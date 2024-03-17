import aws_cdk as core
import aws_cdk.assertions as assertions

from cs40_final.cs40_final_stack import Cs40FinalStack

# example tests. To run these tests, uncomment this file along with the example
# resource in cs40_final/cs40_final_stack.py
def test_sqs_queue_created():
    app = core.App()
    stack = Cs40FinalStack(app, "cs40-final")
    template = assertions.Template.from_stack(stack)

#     template.has_resource_properties("AWS::SQS::Queue", {
#         "VisibilityTimeout": 300
#     })
