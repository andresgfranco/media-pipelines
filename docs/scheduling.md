# Pipeline Scheduling Configuration

## EventBridge Rules

The pipelines can be scheduled using Amazon EventBridge (formerly CloudWatch Events). Below are example configurations for different IaC tools.

### CloudFormation/SAM Example

```yaml
AudioPipelineSchedule:
  Type: AWS::Events::Rule
  Properties:
    Name: media-pipelines-audio-weekly
    Description: Weekly trigger for audio pipeline
    ScheduleExpression: "cron(0 10 ? * MON *)"  # Every Monday at 10:00 UTC
    State: ENABLED
    Targets:
      - Arn: !GetAtt AudioPipelineStateMachine.Arn
        RoleArn: !GetAtt EventBridgeStepFunctionsRole.Arn
        Id: AudioPipelineTarget
        Input: |
          {
            "campaign": "nature",
            "batch_size_audio": 5
          }
```

### AWS CLI Example

```bash
aws events put-rule \
  --name media-pipelines-audio-weekly \
  --schedule-expression "cron(0 10 ? * MON *)" \
  --state ENABLED

aws events put-targets \
  --rule media-pipelines-audio-weekly \
  --targets "Id=1,Arn=arn:aws:states:REGION:ACCOUNT:stateMachine:AudioPipelineStateMachine,RoleArn=arn:aws:iam::ACCOUNT:role/EventBridgeStepFunctionsRole,Input={\"campaign\":\"nature\",\"batch_size_audio\":5}"
```

## SNS Notifications

Optional SNS topic can be configured to receive notifications when pipelines complete:

```bash
# Create topic
aws sns create-topic --name media-pipelines-notifications

# Subscribe email
aws sns subscribe \
  --topic-arn arn:aws:sns:REGION:ACCOUNT:media-pipelines-notifications \
  --protocol email \
  --notification-endpoint your-email@example.com
```

## Local Testing

Use the `schedule_trigger.py` script to simulate scheduled triggers:

```bash
# Trigger audio pipeline
python infrastructure/schedule_trigger.py audio nature 5

# Trigger video pipeline
python infrastructure/schedule_trigger.py video nature 2

# Trigger both
python infrastructure/schedule_trigger.py both nature 5
```
