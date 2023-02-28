# Change Log

All notable changes to this project will be documented in this file.

<a name="unreleased"></a>
## [Unreleased]



<a name="v0.5.0"></a>
## [v0.5.0] - 2023-02-27

- fix!: make name non-nullable ([#16](https://github.com/observeinc/terraform-aws-cloudwatch-logs-subscription/issues/16))
- chore: update changelog


<a name="v0.4.0"></a>
## [v0.4.0] - 2023-02-16

- fix: validate regex for log_group_matches and log_group_excludes ([#13](https://github.com/observeinc/terraform-aws-cloudwatch-logs-subscription/issues/13))
- feat: add tags variable ([#11](https://github.com/observeinc/terraform-aws-cloudwatch-logs-subscription/issues/11))


<a name="v0.3.2"></a>
## [v0.3.2] - 2023-02-08

- chore: update changelog
- docs(description): fix typos, shorten


<a name="v0.3.1"></a>
## [v0.3.1] - 2023-02-08

- chore: update changelog
- make: copy CloudFormation template to S3 as public ([#10](https://github.com/observeinc/terraform-aws-cloudwatch-logs-subscription/issues/10))


<a name="v0.3.0"></a>
## [v0.3.0] - 2022-10-24

- chore: update changelog
- chore: introduce -latest manifest
- improvement: add test cases ([#9](https://github.com/observeinc/terraform-aws-cloudwatch-logs-subscription/issues/9))
- fix: send cloudformation response when lambda times out ([#8](https://github.com/observeinc/terraform-aws-cloudwatch-logs-subscription/issues/8))


<a name="v0.2.0"></a>
## [v0.2.0] - 2022-06-17

- add changelog
- reduce likelihood of hitting a lambda timeout ([#7](https://github.com/observeinc/terraform-aws-cloudwatch-logs-subscription/issues/7))
- avoid leftover log groups ([#5](https://github.com/observeinc/terraform-aws-cloudwatch-logs-subscription/issues/5))
- match all logs by default ([#4](https://github.com/observeinc/terraform-aws-cloudwatch-logs-subscription/issues/4))


<a name="v0.1.0"></a>
## v0.1.0 - 2022-05-18

- improve handling of 'log_group_*' variables ([#2](https://github.com/observeinc/terraform-aws-cloudwatch-logs-subscription/issues/2))
- Add makefile and pre-commit config ([#3](https://github.com/observeinc/terraform-aws-cloudwatch-logs-subscription/issues/3))
- Add first terraform manifests ([#1](https://github.com/observeinc/terraform-aws-cloudwatch-logs-subscription/issues/1))
- Initial commit


[Unreleased]: https://github.com/observeinc/terraform-aws-cloudwatch-logs-subscription/compare/v0.5.0...HEAD
[v0.5.0]: https://github.com/observeinc/terraform-aws-cloudwatch-logs-subscription/compare/v0.4.0...v0.5.0
[v0.4.0]: https://github.com/observeinc/terraform-aws-cloudwatch-logs-subscription/compare/v0.3.2...v0.4.0
[v0.3.2]: https://github.com/observeinc/terraform-aws-cloudwatch-logs-subscription/compare/v0.3.1...v0.3.2
[v0.3.1]: https://github.com/observeinc/terraform-aws-cloudwatch-logs-subscription/compare/v0.3.0...v0.3.1
[v0.3.0]: https://github.com/observeinc/terraform-aws-cloudwatch-logs-subscription/compare/v0.2.0...v0.3.0
[v0.2.0]: https://github.com/observeinc/terraform-aws-cloudwatch-logs-subscription/compare/v0.1.0...v0.2.0
