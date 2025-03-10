from typing import List, Optional

from unittest import TestCase

import boto3
from pathlib import Path

import os

from samcli.cli.global_config import GlobalConfig
from filelock import FileLock
from tests.end_to_end.end_to_end_context import EndToEndTestContext
from tests.testing_utils import CommandResult, run_command, run_command_with_input


class BaseValidator(TestCase):
    def __init__(self, test_context: EndToEndTestContext):
        super().__init__()
        self.test_context = test_context

    def validate(self, command_result: CommandResult):
        self.assertEqual(command_result.process.returncode, 0)


class EndToEndBaseStage(TestCase):
    def __init__(
        self, validator: BaseValidator, test_context: EndToEndTestContext, command_list: Optional[List[str]] = None
    ):
        super().__init__()
        self.validator = validator
        self.command_list = command_list
        self.test_context = test_context

    def run_stage(self) -> CommandResult:
        return run_command(self.command_list, cwd=self.test_context.project_directory)

    def validate(self, command_result: CommandResult):
        self.validator.validate(command_result)


class DefaultInitStage(EndToEndBaseStage):
    def __init__(self, validator, test_context, command_list, app_name):
        super().__init__(validator, test_context, command_list)
        self.app_name = app_name

    def run_stage(self) -> CommandResult:
        config_file_lock = GlobalConfig().config_dir / ".lock"
        with FileLock(str(config_file_lock)):
            # Need to lock the config file so that the several processes don't
            # attempt to write to it at the same time when caching init templates.
            command_result = run_command(self.command_list, cwd=self.test_context.working_directory)
        self._delete_default_samconfig()
        return command_result

    def _delete_default_samconfig(self):
        # The default samconfig.toml has some properties that clash with the test parameters
        default_samconfig = Path(self.test_context.project_directory) / "samconfig.toml"
        try:
            os.remove(default_samconfig)
        except Exception:
            pass


class DefaultRemoteInvokeStage(EndToEndBaseStage):
    def __init__(self, validator, test_context, stack_name):
        super().__init__(validator, test_context)
        self.stack_name = stack_name
        self.lambda_client = boto3.client("lambda")
        self.resource = boto3.resource("cloudformation")

    def run_stage(self) -> CommandResult:
        lambda_output = self.lambda_client.invoke(FunctionName=self._get_lambda_physical_id())
        return CommandResult(lambda_output, "", "")

    def _get_lambda_physical_id(self):
        return self.resource.StackResource(self.stack_name, "HelloWorldFunction").physical_resource_id


class DefaultDeleteStage(EndToEndBaseStage):
    def __init__(self, validator, test_context, command_list, stack_name):
        super().__init__(validator, test_context, command_list)
        self.command_list = command_list
        self.stack_name = stack_name
        self.cfn_client = boto3.client("cloudformation")


class DefaultSyncStage(EndToEndBaseStage):
    def run_stage(self) -> CommandResult:
        return run_command_with_input(self.command_list, "y\n".encode(), cwd=self.test_context.project_directory)
