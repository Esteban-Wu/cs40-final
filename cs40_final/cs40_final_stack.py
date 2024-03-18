from aws_cdk import (
    Tags, Stack,
    aws_ecs as ecs,
    aws_logs as logs,
    aws_ec2 as ec2,
    aws_efs as efs,
    aws_iam as iam,
    aws_route53 as r53,
)
import json, os

from constructs import Construct

class Cs40FinalStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        with open("config.json") as f:
            config = json.load(f)

        # Setup VPC
        vpc = ec2.Vpc(
            self,
            "minecraft-server-vpc",
            availability_zones=["us-west-2a", "us-west-2b"],
            cidr='10.0.0.0/16',
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="Public",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=24
                ),
            ]
        )

        # Setup security groups
        efs_sg = ec2.SecurityGroup(self, 'efs-sg',
            vpc=vpc,
            allow_all_outbound=True,
            description='EFS security group'
        )

        minecraft_sg = ec2.SecurityGroup(self, "minecraft" + '-sg', 
            vpc=vpc,
            allow_all_outbound=True,
            description='minecraft security group'
        )

        minecraft_sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(25565), "minecraft-server from anywhere")
        # efs_sg.add_ingress_rule(peer=ec2.Peer.any_ipv4(), connection=ec2.Port.all_traffic(),
        #                                  description='Allow all traffic')
        # efs_sg.add_egress_rule(peer=ec2.Peer.any_ipv4(), connection=ec2.Port.all_traffic(),
        #                                 description='Allow all traffic')

        efs_sg.add_ingress_rule(minecraft_sg, ec2.Port.tcp(2049), 'Allow clients from minecraft-server')
        # Cody told me to (from ingress)
        minecraft_sg.add_ingress_rule(efs_sg, ec2.Port.tcp(2049), 'Allow efs access for minecraft-server')
        # minecraft_sg.add_ingress_rule(peer=ec2.Peer.any_ipv4(), connection=ec2.Port.all_traffic(),
        #                                  description='Allow all traffic')

        # Create cluster to hold instances
        cluster = ecs.Cluster(self, "MinecraftCluster", vpc=vpc)

        # Create an EFS filesystem and access point
        fs = efs.FileSystem(self, 'minecraft-server-fs', 
                            vpc=vpc,
                            enable_automatic_backups=True,
                            security_group=efs_sg
        )

        # Add an access point
        access_point = efs.AccessPoint(
            self, 
            "minecraft-server-access-point", 
            file_system=fs,  
            path="/minecraft",
            posix_user=efs.PosixUser(
                gid='1000',
                uid='1000',
            ),
            create_acl=efs.Acl(
                owner_gid="1000",
                owner_uid="1000",
                permissions="0755",
            )
        )

        # Define an ECS volume for our EFS filesystem
        volume = ecs.Volume(
            name='minecraft-server-volume',
            efs_volume_configuration=ecs.EfsVolumeConfiguration(
                file_system_id=fs.file_system_id,
                authorization_config=ecs.AuthorizationConfig(
                    access_point_id=access_point.access_point_id,
                    iam="ENABLED"
                ),
                transit_encryption="ENABLED",
            )   
        )

        # Define Fargate Task
        task = ecs.FargateTaskDefinition(self, "minecraft-server", 
            cpu=1024,
            memory_limit_mib=4096,
            task_role=iam.Role(
                self, 
                "minecraft-task-role", 
                assumed_by=iam.ServicePrincipal('ecs-tasks.amazonaws.com'),
                managed_policies=[iam.ManagedPolicy.from_aws_managed_policy_name('service-role/AmazonECSTaskExecutionRolePolicy')],
                inline_policies={
                    "minecraft-task-policy": iam.PolicyDocument(
                        statements=[iam.PolicyStatement(
                            resources=["*"],
                            actions=[
                                "elasticfilesystem:ClientRootAccess",
                                "elasticfilesystem:ClientWrite", 
                                "elasticfilesystem:ClientMount",
                                "elasticfilesystem:DescribeFileSystems"
                            ],
                        )]
                    )
                }
            ),
            volumes=[volume]
        )
        Tags.of(task).add("minecraft-server", "CS40-Final")

        # Define container
        container = task.add_container(
            "minecraft-server",
            image=ecs.ContainerImage.from_registry("itzg/minecraft-server"),
            essential=True,
            environment={
                "EULA": "TRUE", 
                "OPS": config["ops"],
                "ALLOW_NETHER": "true",
                "ENABLE_COMMAND_BLOCK": "true",
                "MAX_TICK_TIME": "60000",
                "MAX_MEMORY": "3600M",
                "TYPE": "VANILLA"
            },
            logging=ecs.LogDrivers.aws_logs(
                stream_prefix="minecraft-server",
                log_retention=logs.RetentionDays.ONE_WEEK,
            )
        )
        container.add_port_mappings(ecs.PortMapping(container_port=25565, host_port=25565))
        container.add_mount_points(ecs.MountPoint(
                                    container_path="/data", 
                                    source_volume=volume.name, 
                                    read_only=False))

        # Create a Fargate Service
        service = ecs.FargateService(self, "minecraft-server-service", 
                                    cluster=cluster, 
                                    task_definition=task,
                                    assign_public_ip=True,
                                    desired_count=1,
                                    security_groups=[minecraft_sg],
                                    propagate_tags=ecs.PropagatedTagSource.SERVICE
                                    )
        # For ease of finding this service and children
        Tags.of(service).add("minecraft-server", "CS40-Final")
        fs.connections.allow_default_port_from(service.connections)
