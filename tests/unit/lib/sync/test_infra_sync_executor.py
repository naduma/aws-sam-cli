from unittest import TestCase
from unittest.mock import MagicMock, patch
from samcli.lib.providers.provider import ResourceIdentifier
from samcli.lib.sync.infra_sync_executor import datetime, InfraSyncExecutor
from botocore.exceptions import ClientError
from parameterized import parameterized


class TestInfraSyncExecutor(TestCase):
    def setUp(self):
        self.build_context = MagicMock()
        self.package_context = MagicMock()
        self.deploy_context = MagicMock()
        self.sync_context = MagicMock()

    @parameterized.expand([(True,), (False,)])
    @patch("samcli.lib.sync.infra_sync_executor.InfraSyncExecutor._auto_skip_infra_sync")
    @patch("samcli.lib.sync.infra_sync_executor.Session")
    @patch("samcli.lib.sync.infra_sync_executor.datetime")
    def test_execute_infra_sync(self, auto_skip_infra_sync, datetime_mock, session_mock, auto_skip_infra_sync_mock):
        datetime_mock.utcnow.return_value = datetime(2023, 2, 8, 12, 12, 12)
        last_infra_sync_time = datetime(2023, 2, 4, 12, 12, 12)
        self.sync_context.get_latest_infra_sync_time.return_value = last_infra_sync_time
        infra_sync_executor = InfraSyncExecutor(
            self.build_context, self.package_context, self.deploy_context, self.sync_context
        )
        auto_skip_infra_sync_mock.return_value = auto_skip_infra_sync
        self.sync_context.get_latest_infra_sync_time.return_value = datetime.utcnow()

        infra_sync_result = infra_sync_executor.execute_infra_sync(True)

        executed = infra_sync_result.infra_sync_executed
        code_sync_resources = infra_sync_result.code_sync_resources

        self.build_context.set_up.assert_called_once()
        self.build_context.run.assert_called_once()
        self.package_context.run.assert_called_once()

        if not auto_skip_infra_sync:
            self.deploy_context.run.assert_called_once()
            self.sync_context.update_infra_sync_time.assert_called_once()
            self.assertEqual(code_sync_resources, set())

        # Reminder: Add back after sync infra skip ready for release
        # self.assertEqual(executed, not auto_skip_infra_sync)

    @patch("samcli.lib.sync.infra_sync_executor.InfraSyncExecutor._auto_skip_infra_sync")
    @patch("samcli.lib.sync.infra_sync_executor.Session")
    @patch("samcli.lib.sync.infra_sync_executor.datetime")
    def test_7_days_auto_execute_infra_sync(self, datetime_mock, session_mock, auto_skip_infra_sync_mock):
        datetime_mock.utcnow.return_value = datetime(2023, 2, 8, 12, 12, 12)
        last_infra_sync_time = datetime(2023, 1, 31, 12, 12, 12)
        self.sync_context.get_latest_infra_sync_time.return_value = last_infra_sync_time
        infra_sync_executor = InfraSyncExecutor(
            self.build_context, self.package_context, self.deploy_context, self.sync_context
        )
        auto_skip_infra_sync_mock.return_value = False
        self.sync_context.get_latest_infra_sync_time.return_value = datetime.utcnow()
        infra_sync_result = infra_sync_executor.execute_infra_sync(True)

        executed = infra_sync_result.infra_sync_executed
        code_sync_resources = infra_sync_result.code_sync_resources

        self.build_context.set_up.assert_called_once()
        self.build_context.run.assert_called_once()
        self.package_context.run.assert_called_once()

        self.deploy_context.run.assert_called_once()

        self.sync_context.update_infra_sync_time.assert_called_once()
        self.assertEqual(code_sync_resources, set())

    @patch("samcli.lib.sync.infra_sync_executor.SYNC_FLOW_THRESHOLD", 1)
    @patch("samcli.lib.sync.infra_sync_executor.InfraSyncExecutor._auto_skip_infra_sync")
    @patch("samcli.lib.sync.infra_sync_executor.Session")
    @patch("samcli.lib.sync.infra_sync_executor.datetime")
    def test_execute_infra_sync_exceed_threshold(self, datetime_mock, session_mock, auto_skip_infra_sync_mock):
        datetime_mock.utcnow.return_value = datetime(2023, 2, 8, 12, 12, 12)
        last_infra_sync_time = datetime(2023, 2, 4, 12, 12, 12)
        self.sync_context.get_latest_infra_sync_time.return_value = last_infra_sync_time
        infra_sync_executor = InfraSyncExecutor(
            self.build_context, self.package_context, self.deploy_context, self.sync_context
        )
        auto_skip_infra_sync_mock.return_value = True
        infra_sync_executor._code_sync_resources = {"Function"}

        infra_sync_result = infra_sync_executor.execute_infra_sync(True)

        executed = infra_sync_result.infra_sync_executed
        code_sync_resources = infra_sync_result.code_sync_resources

        self.build_context.set_up.assert_called_once()
        self.build_context.run.assert_called_once()
        self.package_context.run.assert_called_once()

        self.deploy_context.run.assert_called_once()
        self.assertEqual(code_sync_resources, set())

        self.assertEqual(executed, True)

    @patch("samcli.lib.sync.infra_sync_executor.is_local_path")
    @patch("samcli.lib.sync.infra_sync_executor.get_template_data")
    @patch("samcli.lib.sync.infra_sync_executor.Session")
    def test_auto_skip_infra_sync_basic(self, session_mock, get_template_mock, local_path_mock):
        built_template_dict = {
            "Resources": {
                "ServerlessFunction": {"Type": "AWS::Serverless::Function", "Properties": {"CodeUri": "local/"}}
            }
        }
        packaged_template_dict = {
            "Resources": {
                "ServerlessFunction": {"Type": "AWS::Serverless::Function", "Properties": {"CodeUri": "https://s3_new"}}
            }
        }

        get_template_mock.side_effect = [packaged_template_dict, built_template_dict]
        local_path_mock.return_value = True

        infra_sync_executor = InfraSyncExecutor(
            self.build_context, self.package_context, self.deploy_context, self.sync_context
        )
        infra_sync_executor._cfn_client.get_template.return_value = {
            "TemplateBody": """{
                "Resources": {
                    "ServerlessFunction": {"Type": "AWS::Serverless::Function", "Properties": {"CodeUri": "https://s3"}}
                }
            }"""
        }

        self.assertTrue(infra_sync_executor._auto_skip_infra_sync("path", "path2", "stack_name"))
        self.assertEqual(infra_sync_executor.code_sync_resources, {ResourceIdentifier("ServerlessFunction")})

    @patch("samcli.lib.sync.infra_sync_executor.is_local_path")
    @patch("samcli.lib.sync.infra_sync_executor.get_template_data")
    @patch("samcli.lib.sync.infra_sync_executor.Session")
    def test_auto_skip_infra_sync_all_resources(self, session_mock, get_template_mock, local_path_mock):
        built_template_dict = {
            "Resources": {
                "ServerlessFunction": {
                    "Type": "AWS::Serverless::Function",
                    "Properties": {"CodeUri": "local/", "ImageUri": "image"},
                },
                "LambdaFunction": {
                    "Type": "AWS::Lambda::Function",
                    "Properties": {
                        "Code": {
                            "ImageUri": "image",
                            "S3Bucket": "bucket",
                            "S3Key": "key",
                            "S3ObjectVersion": "version",
                        }
                    },
                },
                "ServerlessLayer": {"Type": "AWS::Serverless::LayerVersion", "Properties": {"ContentUri": "local/"}},
                "LambdaLayer": {"Type": "AWS::Lambda::LayerVersion", "Properties": {"Content": "local/"}},
                "ServerlessApi": {"Type": "AWS::Serverless::Api", "Properties": {"DefinitionUri": "definition"}},
                "RestApi": {"Type": "AWS::ApiGateway::RestApi", "Properties": {"BodyS3Location": "definiton"}},
                "ServerlessHttpApi": {"Type": "AWS::Serverless::HttpApi", "Properties": {"DefinitionUri": "definiton"}},
                "HttpApi": {"Type": "AWS::ApiGatewayV2::Api", "Properties": {"BodyS3Location": "definiton"}},
                "ServerlessStateMachine": {
                    "Type": "AWS::Serverless::StateMachine",
                    "Properties": {"DefinitionUri": "definiton"},
                },
                "StateMachine": {
                    "Type": "AWS::StepFunctions::StateMachine",
                    "Properties": {"DefinitionS3Location": "definiton"},
                },
            }
        }

        packaged_template_dict = {
            "Resources": {
                "ServerlessFunction": {
                    "Type": "AWS::Serverless::Function",
                    "Properties": {"CodeUri": "s3://location2", "ImageUri": "s3://location2"},
                },
                "LambdaFunction": {
                    "Type": "AWS::Lambda::Function",
                    "Properties": {
                        "Code": {
                            "ImageUri": "s3://location2",
                            "S3Bucket": "s3://location2",
                            "S3Key": "s3://location2",
                            "S3ObjectVersion": "s3://location2",
                        }
                    },
                },
                "ServerlessLayer": {
                    "Type": "AWS::Serverless::LayerVersion",
                    "Properties": {"ContentUri": "s3://location2"},
                },
                "LambdaLayer": {"Type": "AWS::Lambda::LayerVersion", "Properties": {"Content": "s3://location2"}},
                "ServerlessApi": {"Type": "AWS::Serverless::Api", "Properties": {"DefinitionUri": "s3://location2"}},
                "RestApi": {"Type": "AWS::ApiGateway::RestApi", "Properties": {"BodyS3Location": "s3://location2"}},
                "ServerlessHttpApi": {
                    "Type": "AWS::Serverless::HttpApi",
                    "Properties": {"DefinitionUri": "s3://location2"},
                },
                "HttpApi": {"Type": "AWS::ApiGatewayV2::Api", "Properties": {"BodyS3Location": "s3://location2"}},
                "ServerlessStateMachine": {
                    "Type": "AWS::Serverless::StateMachine",
                    "Properties": {"DefinitionUri": "s3://location2"},
                },
                "StateMachine": {
                    "Type": "AWS::StepFunctions::StateMachine",
                    "Properties": {"DefinitionS3Location": "s3://location2"},
                },
            }
        }

        get_template_mock.side_effect = [
            packaged_template_dict,
            built_template_dict,
            packaged_template_dict,
            built_template_dict,
        ]
        local_path_mock.return_value = True

        infra_sync_executor = InfraSyncExecutor(
            self.build_context, self.package_context, self.deploy_context, self.sync_context
        )
        infra_sync_executor._cfn_client.get_template.return_value = {
            "TemplateBody": """{
                "Resources": {
                    "ServerlessFunction": {
                        "Type": "AWS::Serverless::Function",
                        "Properties": {"CodeUri": "s3://location", "ImageUri": "s3://location"},
                    },
                    "LambdaFunction": {
                        "Type": "AWS::Lambda::Function",
                        "Properties": {
                            "Code": {
                                "ImageUri": "s3://location",
                                "S3Bucket": "s3://location",
                                "S3Key": "s3://location",
                                "S3ObjectVersion": "s3://location",
                            }
                        },
                    },
                    "ServerlessLayer": {
                        "Type": "AWS::Serverless::LayerVersion",
                        "Properties": {"ContentUri": "s3://location"},
                    },
                    "LambdaLayer": {"Type": "AWS::Lambda::LayerVersion", "Properties": {"Content": "s3://location"}},
                    "ServerlessApi": {"Type": "AWS::Serverless::Api", "Properties": {"DefinitionUri": "s3://location"}},
                    "RestApi": {"Type": "AWS::ApiGateway::RestApi", "Properties": {"BodyS3Location": "s3://location"}},
                    "ServerlessHttpApi": {
                        "Type": "AWS::Serverless::HttpApi",
                        "Properties": {"DefinitionUri": "s3://location"},
                    },
                    "HttpApi": {"Type": "AWS::ApiGatewayV2::Api", "Properties": {"BodyS3Location": "s3://location"}},
                    "ServerlessStateMachine": {
                        "Type": "AWS::Serverless::StateMachine",
                        "Properties": {"DefinitionUri": "s3://location"},
                    },
                    "StateMachine": {
                        "Type": "AWS::StepFunctions::StateMachine",
                        "Properties": {"DefinitionS3Location": "s3://location"},
                    },
                }
            }"""
        }

        self.assertTrue(infra_sync_executor._auto_skip_infra_sync("path", "path2", "stack_name"))
        self.assertEqual(
            infra_sync_executor.code_sync_resources,
            {
                ResourceIdentifier("HttpApi"),
                ResourceIdentifier("LambdaFunction"),
                ResourceIdentifier("LambdaLayer"),
                ResourceIdentifier("RestApi"),
                ResourceIdentifier("ServerlessApi"),
                ResourceIdentifier("ServerlessFunction"),
                ResourceIdentifier("ServerlessHttpApi"),
                ResourceIdentifier("ServerlessLayer"),
                ResourceIdentifier("ServerlessStateMachine"),
                ResourceIdentifier("StateMachine"),
            },
        )

        local_path_mock.return_value = False
        self.assertFalse(infra_sync_executor._auto_skip_infra_sync("path", "path2", "stack_name"))

    @patch("samcli.lib.sync.infra_sync_executor.is_local_path")
    @patch("samcli.lib.sync.infra_sync_executor.get_template_data")
    @patch("samcli.lib.sync.infra_sync_executor.Session")
    def test_auto_skip_infra_sync_nested_stack(self, session_mock, get_template_mock, local_path_mock):
        built_template_dict = {
            "Resources": {
                "ServerlessApplication": {"Type": "AWS::Serverless::Application", "Properties": {"Location": "local/"}},
            }
        }

        packaged_template_dict = {
            "Resources": {
                "ServerlessApplication": {
                    "Type": "AWS::Serverless::Application",
                    "Properties": {"Location": "https://s3.com/bucket/key"},
                },
            }
        }

        built_nested_dict = {
            "Resources": {
                "ServerlessFunction": {"Type": "AWS::Serverless::Function", "Properties": {"CodeUri": "local/"}}
            }
        }

        packaged_nested_dict = """{
            "Resources": {
                "ServerlessFunction": {"Type": "AWS::Serverless::Function", "Properties": {"CodeUri": "https://s3.com/bucket/key"}}
            }
        }"""

        get_template_mock.side_effect = [packaged_template_dict, built_template_dict, built_nested_dict]
        local_path_mock.return_value = True

        infra_sync_executor = InfraSyncExecutor(
            self.build_context, self.package_context, self.deploy_context, self.sync_context
        )
        infra_sync_executor._cfn_client.get_template.side_effect = [
            {
                "TemplateBody": """{
                    "Resources": {
                        "ServerlessApplication": {"Type": "AWS::Serverless::Application", "Properties": {"Location": "local/"}}
                    }
                }"""
            },
            {
                "TemplateBody": """{
                    "Resources": {
                        "ServerlessFunction": {"Type": "AWS::Serverless::Function", "Properties": {"CodeUri": "local/"}}
                    }
                }"""
            },
        ]

        infra_sync_executor._cfn_client.describe_stack_resource.return_value = {
            "StackResourceDetails": {"PhysicalResourceId": "id"}
        }

        with patch("botocore.response.StreamingBody") as stream_mock:
            stream_mock.read.return_value = packaged_nested_dict.encode("utf-8")
            infra_sync_executor._s3_client.get_object.return_value = {"Body": stream_mock}
            self.assertTrue(infra_sync_executor._auto_skip_infra_sync("path", "path", "stack_name"))
            self.assertEqual(
                infra_sync_executor.code_sync_resources,
                {ResourceIdentifier("ServerlessApplication/ServerlessFunction")},
            )

    @parameterized.expand([(True, "sar_id"), (False, "sar_id_2")])
    @patch("samcli.lib.sync.infra_sync_executor.is_local_path")
    @patch("samcli.lib.sync.infra_sync_executor.get_template_data")
    @patch("samcli.lib.sync.infra_sync_executor.Session")
    def test_auto_skip_infra_sync_nested_stack_with_sar(
        self, expected_result, sar_id, session_mock, get_template_mock, local_path_mock
    ):
        built_template_dict = {
            "Resources": {
                "ServerlessApplication": {
                    "Type": "AWS::Serverless::Application",
                    "Properties": {"Location": {"ApplicationId": sar_id, "SemanticVersion": "version"}},
                }
            }
        }

        packaged_template_dict = {
            "Resources": {
                "ServerlessApplication": {
                    "Type": "AWS::Serverless::Application",
                    "Properties": {"Location": {"ApplicationId": sar_id, "SemanticVersion": "version"}},
                }
            }
        }

        get_template_mock.side_effect = [packaged_template_dict, built_template_dict]
        local_path_mock.return_value = True

        infra_sync_executor = InfraSyncExecutor(
            self.build_context, self.package_context, self.deploy_context, self.sync_context
        )
        infra_sync_executor._cfn_client.get_template.side_effect = [
            {
                "TemplateBody": """{
                    "Resources": {
                        "ServerlessApplication": {
                            "Type": "AWS::Serverless::Application",
                            "Properties": {"Location": {"ApplicationId": "sar_id", "SemanticVersion": "version"}},
                        }
                    }
                }"""
            },
        ]

        infra_sync_executor._cfn_client.describe_stack_resource.return_value = {
            "StackResourceDetails": {"PhysicalResourceId": "id"}
        }

        self.assertEqual(infra_sync_executor._auto_skip_infra_sync("path", "path2", "stack_name"), expected_result)
        self.assertEqual(infra_sync_executor.code_sync_resources, set())

    @patch("samcli.lib.sync.infra_sync_executor.is_local_path")
    @patch("samcli.lib.sync.infra_sync_executor.get_template_data")
    @patch("samcli.lib.sync.infra_sync_executor.Session")
    def test_auto_skip_infra_sync_http_template_location(self, session_mock, get_template_mock, local_path_mock):
        built_template_dict = {
            "Resources": {
                "NestedStack": {
                    "Type": "AWS::CloudFormation::Stack",
                    "Properties": {"TemplateURL": "https://s3.com/bucket/key"},
                }
            }
        }

        packaged_template_dict = {
            "Resources": {
                "NestedStack": {
                    "Type": "AWS::CloudFormation::Stack",
                    "Properties": {"TemplateURL": "https://s3.com/bucket/key"},
                }
            }
        }

        nested_dict = """{
            "Resources": {
                "ServerlessFunction": {"Type": "AWS::Serverless::Function", "Properties": {"CodeUri": "local/"}}
            }
        }"""

        get_template_mock.side_effect = [packaged_template_dict, built_template_dict]
        local_path_mock.return_value = True

        infra_sync_executor = InfraSyncExecutor(
            self.build_context, self.package_context, self.deploy_context, self.sync_context
        )
        infra_sync_executor._cfn_client.get_template.side_effect = [
            {
                "TemplateBody": """{
                    Resources: {
                        "NestedStack": {
                            "Type": "AWS::CloudFormation::Stack",
                            "Properties": {"TemplateURL": "https://s3.com/bucket/key"}
                        }
                    }
                }"""
            },
            {
                "TemplateBody": """{
                    "Resources": {
                        "ServerlessFunction": {"Type": "AWS::Serverless::Function", "Properties": {"CodeUri": "local/"}}
                    }
                }"""
            },
        ]

        infra_sync_executor._cfn_client.describe_stack_resource.return_value = {
            "StackResourceDetails": {"PhysicalResourceId": "id"}
        }

        with patch("botocore.response.StreamingBody") as stream_mock:
            stream_mock.read.return_value = nested_dict.encode("utf-8")
            infra_sync_executor._s3_client.get_object.return_value = {"Body": stream_mock}
            self.assertTrue(infra_sync_executor._auto_skip_infra_sync("path", "path2", "stack_name"))
            self.assertEqual(infra_sync_executor.code_sync_resources, set())

    @patch("samcli.lib.sync.infra_sync_executor.is_local_path")
    @patch("samcli.lib.sync.infra_sync_executor.get_template_data")
    @patch("samcli.lib.sync.infra_sync_executor.Session")
    def test_auto_skip_infra_sync_exception(self, session_mock, get_template_mock, local_path_mock):
        template_dict = {
            "Resources": {
                "ServerlessApplication": {
                    "Type": "AWS::Serverless::Application",
                    "Properties": {"Location": "https://s3.com/bucket/key"},
                }
            }
        }

        get_template_mock.return_value = template_dict
        local_path_mock.return_value = True

        infra_sync_executor = InfraSyncExecutor(
            self.build_context, self.package_context, self.deploy_context, self.sync_context
        )
        infra_sync_executor._cfn_client.get_template.side_effect = [ClientError({"Error": {"Code": "404"}}, "Error")]

        self.assertFalse(infra_sync_executor._auto_skip_infra_sync("path", "path2", "stack_name"))

    @patch("samcli.lib.sync.infra_sync_executor.is_local_path")
    @patch("samcli.lib.sync.infra_sync_executor.Session")
    def test_sanitize_template(self, session_mock, local_path_mock):
        built_template_dict = {
            "Resources": {
                "ServerlessFunction": {
                    "Type": "AWS::Serverless::Function",
                    "Properties": {"CodeUri": "local/", "ImageUri": "image"},
                },
                "LambdaFunction": {
                    "Type": "AWS::Lambda::Function",
                    "Properties": {
                        "Code": {
                            "ImageUri": "image",
                            "S3Bucket": "bucket",
                            "S3Key": "key",
                            "S3ObjectVersion": "version",
                        }
                    },
                },
                "ServerlessLayer": {"Type": "AWS::Serverless::LayerVersion", "Properties": {"ContentUri": "local/"}},
                "LambdaLayer": {"Type": "AWS::Lambda::LayerVersion", "Properties": {"Content": "local/"}},
                "ServerlessApi": {"Type": "AWS::Serverless::Api", "Properties": {"DefinitionUri": "definition"}},
                "RestApi": {"Type": "AWS::ApiGateway::RestApi", "Properties": {"BodyS3Location": "definiton"}},
                "ServerlessHttpApi": {"Type": "AWS::Serverless::HttpApi", "Properties": {"DefinitionUri": "definiton"}},
                "HttpApi": {"Type": "AWS::ApiGatewayV2::Api", "Properties": {"BodyS3Location": "definiton"}},
                "ServerlessStateMachine": {
                    "Type": "AWS::Serverless::StateMachine",
                    "Properties": {"DefinitionUri": "definiton"},
                },
                "StateMachine": {
                    "Type": "AWS::StepFunctions::StateMachine",
                    "Properties": {"DefinitionS3Location": "definiton"},
                },
                "ServerlessApplication": {
                    "Type": "AWS::Serverless::Application",
                    "Properties": {"Location": "template"},
                },
                "NestedStack": {"Type": "AWS::CloudFormation::Stack", "Properties": {"TemplateURL": "http://s3"}},
            }
        }

        packaged_template_dict = {
            "Resources": {
                "ServerlessFunction": {
                    "Type": "AWS::Serverless::Function",
                    "Properties": {"CodeUri": "s3://location", "ImageUri": "s3://location"},
                },
                "LambdaFunction": {
                    "Type": "AWS::Lambda::Function",
                    "Properties": {
                        "Code": {
                            "ImageUri": "s3://location",
                            "S3Bucket": "s3://location",
                            "S3Key": "s3://location",
                            "S3ObjectVersion": "s3://location",
                        }
                    },
                },
                "ServerlessLayer": {
                    "Type": "AWS::Serverless::LayerVersion",
                    "Properties": {"ContentUri": "s3://location"},
                },
                "LambdaLayer": {"Type": "AWS::Lambda::LayerVersion", "Properties": {"Content": "s3://location"}},
                "ServerlessApi": {"Type": "AWS::Serverless::Api", "Properties": {"DefinitionUri": "s3://location"}},
                "RestApi": {"Type": "AWS::ApiGateway::RestApi", "Properties": {"BodyS3Location": "s3://location"}},
                "ServerlessHttpApi": {
                    "Type": "AWS::Serverless::HttpApi",
                    "Properties": {"DefinitionUri": "s3://location"},
                },
                "HttpApi": {"Type": "AWS::ApiGatewayV2::Api", "Properties": {"BodyS3Location": "s3://location"}},
                "ServerlessStateMachine": {
                    "Type": "AWS::Serverless::StateMachine",
                    "Properties": {"DefinitionUri": "s3://location"},
                },
                "StateMachine": {
                    "Type": "AWS::StepFunctions::StateMachine",
                    "Properties": {"DefinitionS3Location": "s3://location"},
                },
                "ServerlessApplication": {
                    "Type": "AWS::Serverless::Application",
                    "Properties": {"Location": "https://s3"},
                },
                "NestedStack": {"Type": "AWS::CloudFormation::Stack", "Properties": {"TemplateURL": "https://s3"}},
            }
        }

        expected_resources = {
            "ServerlessFunction",
            "LambdaFunction",
            "ServerlessLayer",
            "LambdaLayer",
            "ServerlessApi",
            "RestApi",
            "ServerlessHttpApi",
            "HttpApi",
            "ServerlessStateMachine",
            "StateMachine",
            "ServerlessApplication",
            "NestedStack",
        }

        local_path_mock.return_value = True
        infra_sync_executor = InfraSyncExecutor(
            self.build_context, self.package_context, self.deploy_context, self.sync_context
        )

        processed_resources = infra_sync_executor._sanitize_template(packaged_template_dict, set(), built_template_dict)

        self.assertEqual(processed_resources, expected_resources)

        expected_dict = {
            "Resources": {
                "ServerlessFunction": {
                    "Type": "AWS::Serverless::Function",
                    "Properties": {},
                },
                "LambdaFunction": {
                    "Type": "AWS::Lambda::Function",
                    "Properties": {"Code": {}},
                },
                "ServerlessLayer": {
                    "Type": "AWS::Serverless::LayerVersion",
                    "Properties": {},
                },
                "LambdaLayer": {"Type": "AWS::Lambda::LayerVersion", "Properties": {}},
                "ServerlessApi": {"Type": "AWS::Serverless::Api", "Properties": {}},
                "RestApi": {"Type": "AWS::ApiGateway::RestApi", "Properties": {}},
                "ServerlessHttpApi": {
                    "Type": "AWS::Serverless::HttpApi",
                    "Properties": {},
                },
                "HttpApi": {"Type": "AWS::ApiGatewayV2::Api", "Properties": {}},
                "ServerlessStateMachine": {
                    "Type": "AWS::Serverless::StateMachine",
                    "Properties": {},
                },
                "StateMachine": {
                    "Type": "AWS::StepFunctions::StateMachine",
                    "Properties": {},
                },
                "ServerlessApplication": {"Type": "AWS::Serverless::Application", "Properties": {}},
                "NestedStack": {"Type": "AWS::CloudFormation::Stack", "Properties": {}},
            }
        }

        self.assertEqual(packaged_template_dict, expected_dict)

        downloaded_template_dict = {
            "Resources": {
                "ServerlessFunction": {
                    "Type": "AWS::Serverless::Function",
                    "Properties": {"CodeUri": "s3://location", "ImageUri": "s3://location"},
                },
                "LambdaFunction": {
                    "Type": "AWS::Lambda::Function",
                    "Properties": {
                        "Code": {
                            "ImageUri": "s3://location",
                            "S3Bucket": "s3://location",
                            "S3Key": "s3://location",
                            "S3ObjectVersion": "s3://location",
                        }
                    },
                },
                "ServerlessLayer": {
                    "Type": "AWS::Serverless::LayerVersion",
                    "Properties": {"ContentUri": "s3://location"},
                },
                "LambdaLayer": {"Type": "AWS::Lambda::LayerVersion", "Properties": {"Content": "s3://location"}},
                "ServerlessApi": {"Type": "AWS::Serverless::Api", "Properties": {"DefinitionUri": "s3://location"}},
                "RestApi": {"Type": "AWS::ApiGateway::RestApi", "Properties": {"BodyS3Location": "s3://location"}},
                "ServerlessHttpApi": {
                    "Type": "AWS::Serverless::HttpApi",
                    "Properties": {"DefinitionUri": "s3://location"},
                },
                "HttpApi": {"Type": "AWS::ApiGatewayV2::Api", "Properties": {"BodyS3Location": "s3://location"}},
                "ServerlessStateMachine": {
                    "Type": "AWS::Serverless::StateMachine",
                    "Properties": {"DefinitionUri": "s3://location"},
                },
                "StateMachine": {
                    "Type": "AWS::StepFunctions::StateMachine",
                    "Properties": {"DefinitionS3Location": "s3://location"},
                },
                "ServerlessApplication": {
                    "Type": "AWS::Serverless::Application",
                    "Properties": {"Location": "https://s3"},
                },
                "NestedStack": {"Type": "AWS::CloudFormation::Stack", "Properties": {"TemplateURL": "https://s3"}},
            }
        }

        processed_resources = infra_sync_executor._sanitize_template(downloaded_template_dict, expected_resources)
        self.assertEqual(processed_resources, expected_resources)

        self.assertEqual(downloaded_template_dict, expected_dict)

    @patch("samcli.lib.sync.infra_sync_executor.is_local_path")
    @patch("samcli.lib.sync.infra_sync_executor.Session")
    def test_remove_metadata(self, session_mock, local_path_mock):
        template_dict = {
            "Resources": {
                "ServerlessFunction": {
                    "Type": "AWS::Serverless::Function",
                    "Properties": {"CodeUri": "https://s3", "ImageUri": "https://s3"},
                    "Metadata": {"SamResourceId": "Id"},
                }
            }
        }

        expected_dict = {
            "Resources": {
                "ServerlessFunction": {
                    "Type": "AWS::Serverless::Function",
                    "Properties": {"CodeUri": "https://s3", "ImageUri": "https://s3"},
                }
            }
        }

        local_path_mock.return_value = True
        infra_sync_executor = InfraSyncExecutor(
            self.build_context, self.package_context, self.deploy_context, self.sync_context
        )

        infra_sync_executor._sanitize_template(template_dict, set())

        self.assertEqual(template_dict, expected_dict)

    @parameterized.expand([(True, []), (False, ["ServerlessFunction"])])
    @patch("samcli.lib.sync.infra_sync_executor.is_local_path")
    @patch("samcli.lib.sync.infra_sync_executor.Session")
    def test_remove_resource_field(self, is_local_path, linked_resources, session_mock, local_path_mock):
        built_resource_dict = {
            "Type": "AWS::Serverless::Function",
            "Properties": {"CodeUri": "local/", "ImageUri": "image"},
        }

        resource_dict = {
            "Type": "AWS::Serverless::Function",
            "Properties": {"CodeUri": "https://s3", "ImageUri": "https://s3"},
        }

        expected_dict = {
            "Type": "AWS::Serverless::Function",
            "Properties": {},
        }

        resource_type = "AWS::Serverless::Function"
        serverless_resource_id = "ServerlessFunction"

        local_path_mock.return_value = is_local_path
        infra_sync_executor = InfraSyncExecutor(
            self.build_context, self.package_context, self.deploy_context, self.sync_context
        )

        processed_resource = infra_sync_executor._remove_resource_field(
            serverless_resource_id, resource_type, resource_dict, linked_resources, built_resource_dict
        )

        self.assertEqual(processed_resource, serverless_resource_id)
        self.assertEqual(resource_dict, expected_dict)

    @parameterized.expand([(True, []), (False, ["LambdaFunction"])])
    @patch("samcli.lib.sync.infra_sync_executor.is_local_path")
    @patch("samcli.lib.sync.infra_sync_executor.Session")
    def test_remove_resource_field_lambda_function(
        self, is_local_path, linked_resources, session_mock, local_path_mock
    ):
        resource_dict = {
            "Type": "AWS::Lambda::Function",
            "Properties": {
                "Code": {
                    "ZipFile": "inline code",
                    "ImageUri": "s3://location",
                    "S3Bucket": "s3://location",
                    "S3Key": "s3://location",
                    "S3ObjectVersion": "s3://location",
                }
            },
        }

        expected_dict = {
            "Type": "AWS::Lambda::Function",
            "Properties": {"Code": {"ZipFile": "inline code"}},
        }

        resource_type = "AWS::Lambda::Function"
        lambda_resource_id = "LambdaFunction"

        local_path_mock.return_value = is_local_path
        infra_sync_executor = InfraSyncExecutor(
            self.build_context, self.package_context, self.deploy_context, self.sync_context
        )

        processed_resource = infra_sync_executor._remove_resource_field(
            lambda_resource_id, resource_type, resource_dict, linked_resources, resource_dict
        )

        self.assertEqual(processed_resource, lambda_resource_id)
        self.assertEqual(resource_dict, expected_dict)

    @parameterized.expand([(True, []), (False, ["LambdaFunction"])])
    @patch("samcli.lib.sync.infra_sync_executor.is_local_path")
    @patch("samcli.lib.sync.infra_sync_executor.Session")
    def test_remove_resource_field_lambda_function_code_string(
        self, is_local_path, linked_resources, session_mock, local_path_mock
    ):
        built_resource_dict = {
            "Type": "AWS::Lambda::Function",
            "Properties": {"Code": "local"},
        }

        packaged_resource_dict = {
            "Type": "AWS::Lambda::Function",
            "Properties": {"Code": {"S3Bucket": "bucket", "S3Key": "key"}},
        }

        expected_dict = {
            "Type": "AWS::Lambda::Function",
            "Properties": {"Code": {}},
        }

        resource_type = "AWS::Lambda::Function"
        lambda_resource_id = "LambdaFunction"

        local_path_mock.return_value = is_local_path
        infra_sync_executor = InfraSyncExecutor(
            self.build_context, self.package_context, self.deploy_context, self.sync_context
        )

        processed_resource = infra_sync_executor._remove_resource_field(
            lambda_resource_id, resource_type, packaged_resource_dict, linked_resources, built_resource_dict
        )

        self.assertEqual(processed_resource, lambda_resource_id)
        self.assertEqual(packaged_resource_dict, expected_dict)

    @patch("samcli.lib.sync.infra_sync_executor.get_template_data")
    @patch("samcli.lib.sync.infra_sync_executor.InfraSyncExecutor._get_remote_template_data")
    @patch("samcli.lib.sync.infra_sync_executor.Session")
    def test_get_templates(self, session_mock, get_remote_template_mock, get_template_mock):
        infra_sync_executor = InfraSyncExecutor(
            self.build_context, self.package_context, self.deploy_context, self.sync_context
        )

        infra_sync_executor.get_template("local")
        get_template_mock.assert_called_once_with("local")

        infra_sync_executor.get_template("https://s3.com/key/value")
        get_remote_template_mock.assert_called_once_with("https://s3.com/key/value")

    @patch("samcli.lib.sync.infra_sync_executor.Session")
    def test_get_remote_template(self, sessiion_mock):
        self.template_dict = {
            "Resources": {
                "ServerlessApplication": {
                    "Type": "AWS::Serverless::Application",
                    "Properties": {"Location": "https://s3.com/bucket/key"},
                }
            }
        }

        s3_string = """{
            "Resources": {
                "ServerlessApplication": {
                    "Type": "AWS::Serverless::Application",
                    "Properties": {"Location": "https://s3.com/bucket/key"},
                }
            }
        }"""

        infra_sync_executor = InfraSyncExecutor(
            self.build_context, self.package_context, self.deploy_context, self.sync_context
        )

        with patch("botocore.response.StreamingBody") as stream_mock:
            stream_mock.read.return_value = s3_string.encode("utf-8")
            infra_sync_executor._s3_client.get_object.return_value = {"Body": stream_mock}

            self.assertEqual(
                infra_sync_executor._get_remote_template_data("https://s3.com/key/value"), self.template_dict
            )
