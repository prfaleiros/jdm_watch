#!/usr/bin/env python3
import aws_cdk as cdk
from stacks.watch_stack import WatchBusinessStack

app = cdk.App()
WatchBusinessStack(app, "JdmWatchBusiness", env=cdk.Environment(
    account=app.node.try_get_context("account"),
    region="us-east-1"
))
app.synth()
