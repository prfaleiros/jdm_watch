from aws_cdk import (
    Stack, Duration, RemovalPolicy, CfnOutput,
    aws_dynamodb as ddb,
    aws_s3 as s3,
    aws_lambda as _lambda,
    aws_apigateway as apigw
)
from constructs import Construct
import os

LAMBDAS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "lambdas")


class WatchBusinessStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs):
        super().__init__(scope, construct_id, **kwargs)

        table = ddb.Table(
            self, "WatchTable",
            table_name="WatchBusiness",
            partition_key=ddb.Attribute(name="PK", type=ddb.AttributeType.STRING),
            sort_key=ddb.Attribute(name="SK", type=ddb.AttributeType.STRING),
            billing_mode=ddb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.RETAIN,
        )
        table.add_global_secondary_index(
            index_name="GSI1",
            partition_key=ddb.Attribute(name="GSI1PK", type=ddb.AttributeType.STRING),
            sort_key=ddb.Attribute(name="GSI1SK", type=ddb.AttributeType.STRING),
            projection_type=ddb.ProjectionType.ALL,
        )

        config_bucket = s3.Bucket(self, "ConfigBucket",
            removal_policy=RemovalPolicy.RETAIN,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
        )
        photos_bucket = s3.Bucket(self, "PhotosBucket",
            removal_policy=RemovalPolicy.RETAIN,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            cors=[s3.CorsRule(
                allowed_methods=[s3.HttpMethods.PUT, s3.HttpMethods.GET],
                allowed_origins=["*"],
                allowed_headers=["*"],
                max_age=3600,
            )],
        )

        shared_layer = _lambda.LayerVersion(
            self, "SharedLayer",
            code=_lambda.Code.from_asset(os.path.join(LAMBDAS_DIR, "shared")),
            compatible_runtimes=[_lambda.Runtime.PYTHON_3_12],
        )

        common_env = {
            "TABLE_NAME": table.table_name,
            "CONFIG_BUCKET": config_bucket.bucket_name,
            "PHOTOS_BUCKET": photos_bucket.bucket_name,
            "CONFIG_KEY": "config.json",
        }

        def make_fn(id, path):
            fn = _lambda.Function(self, id,
                runtime=_lambda.Runtime.PYTHON_3_12,
                handler="handler.handler",
                code=_lambda.Code.from_asset(os.path.join(LAMBDAS_DIR, *path.split("/"))),
                layers=[shared_layer],
                environment=common_env,
                timeout=Duration.seconds(15),
                memory_size=256,
            )
            table.grant_read_write_data(fn)
            config_bucket.grant_read(fn)
            return fn

        watch_create     = make_fn("WatchCreate",     "watches/create")
        watch_get        = make_fn("WatchGet",        "watches/get")
        watch_list       = make_fn("WatchList",       "watches/list")
        watch_update     = make_fn("WatchUpdate",     "watches/update")
        watch_delete     = make_fn("WatchDelete",     "watches/delete")
        watch_transition = make_fn("WatchTransition", "watches/transition")
        cost_add         = make_fn("CostAdd",         "costs/add")
        cost_update      = make_fn("CostUpdate",      "costs/update")
        cost_delete      = make_fn("CostDelete",      "costs/delete")
        shipment_create  = make_fn("ShipmentCreate",  "shipments/create")
        shipment_allocate= make_fn("ShipmentAllocate","shipments/allocate")
        campaign_create  = make_fn("CampaignCreate",  "campaigns/create")
        campaign_allocate= make_fn("CampaignAllocate","campaigns/allocate")
        pricing_forward  = make_fn("PricingForward",  "pricing/forward")
        pricing_backward = make_fn("PricingBackward", "pricing/backward")
        report_listing   = make_fn("ReportListing",   "reports/listing")
        photo_presign    = make_fn("PhotoPresign",     "photos/presign")
        sale_close       = make_fn("SaleClose",        "sales/close")
        photos_bucket.grant_put(photo_presign)
        photos_bucket.grant_read(photo_presign)
        photos_bucket.grant_read(report_listing)
        photos_bucket.grant_read(watch_list)   # presigned GET URLs for thumbnails

        # --- API Gateway ---
        api = apigw.RestApi(self, "WatchApi",
            rest_api_name="JDM Watch Business",
            default_cors_preflight_options=apigw.CorsOptions(
                allow_origins=apigw.Cors.ALL_ORIGINS,
                allow_methods=apigw.Cors.ALL_METHODS,
            ),
        )
        api_key = api.add_api_key("WatchApiKey")
        plan = api.add_usage_plan("WatchUsagePlan",
            throttle=apigw.ThrottleSettings(rate_limit=10, burst_limit=20),
        )
        plan.add_api_key(api_key)
        plan.add_api_stage(stage=api.deployment_stage)

        ak = True  # api_key_required

        watches = api.root.add_resource("watches")
        watches.add_method("POST", apigw.LambdaIntegration(watch_create), api_key_required=ak)
        watches.add_method("GET", apigw.LambdaIntegration(watch_list), api_key_required=ak)

        watch = watches.add_resource("{id}")
        watch.add_method("GET",    apigw.LambdaIntegration(watch_get),    api_key_required=ak)
        watch.add_method("PATCH",  apigw.LambdaIntegration(watch_update), api_key_required=ak)
        watch.add_method("DELETE", apigw.LambdaIntegration(watch_delete), api_key_required=ak)

        watch.add_resource("transitions").add_method("POST", apigw.LambdaIntegration(watch_transition), api_key_required=ak)
        costs_resource = watch.add_resource("costs")
        costs_resource.add_method("POST", apigw.LambdaIntegration(cost_add), api_key_required=ak)
        cost_item = costs_resource.add_resource("{cost_id}")
        cost_item.add_method("PATCH",  apigw.LambdaIntegration(cost_update), api_key_required=ak)
        cost_item.add_method("DELETE", apigw.LambdaIntegration(cost_delete), api_key_required=ak)
        watch.add_resource("pricing").add_method("GET", apigw.LambdaIntegration(pricing_forward), api_key_required=ak)
        watch.add_resource("listing-report").add_method("GET", apigw.LambdaIntegration(report_listing), api_key_required=ak)
        watch.add_resource("upload-url").add_method("GET", apigw.LambdaIntegration(photo_presign), api_key_required=ak)
        watch.add_resource("close").add_method("POST", apigw.LambdaIntegration(sale_close), api_key_required=ak)

        shipments = api.root.add_resource("shipments")
        shipments.add_method("POST", apigw.LambdaIntegration(shipment_create), api_key_required=ak)
        shipments.add_resource("{id}").add_resource("allocate").add_method("POST", apigw.LambdaIntegration(shipment_allocate), api_key_required=ak)

        campaigns = api.root.add_resource("campaigns")
        campaigns.add_method("POST", apigw.LambdaIntegration(campaign_create), api_key_required=ak)
        campaigns.add_resource("{id}").add_resource("allocate").add_method("POST", apigw.LambdaIntegration(campaign_allocate), api_key_required=ak)

        pricing_root = api.root.add_resource("pricing")
        pricing_root.add_resource("max-bid").add_method("POST", apigw.LambdaIntegration(pricing_backward), api_key_required=ak)

        CfnOutput(self, "ApiUrl", value=api.url)

        CfnOutput(self, "ConfigBucketName", value=config_bucket.bucket_name)
        CfnOutput(self, "PhotosBucketName", value=photos_bucket.bucket_name)