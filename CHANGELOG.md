# Changelog

## [0.2.2](https://github.com/bedrock-python/mattermind/compare/mattermind-v0.2.1...mattermind-v0.2.2) (2026-10-07)


### Bug Fixes

* ship py.typed and point the changelog link at master ([#43](https://github.com/bedrock-python/mattermind/issues/43)) ([9547230](https://github.com/bedrock-python/mattermind/commit/9547230f63433baf1b9070a6df5e98ad2556a0ed))

## [0.2.1](https://github.com/bedrock-python/mattermind/compare/mattermind-v0.2.0...mattermind-v0.2.1) (2026-09-14)


### Bug Fixes

* **deps:** bump openai from 2.36.0 to 3.13.0 and use its httpx2 client ([dabe227](https://github.com/bedrock-python/mattermind/commit/dabe227cea1133ba28ce39b5255d8d14708aab15))

## [0.2.0](https://github.com/bedrock-python/mattermind/compare/mattermind-v0.1.1...mattermind-v0.2.0) (2026-09-06)


### ⚠ BREAKING CHANGES

* a configuration file carrying a key no other version of mattermind reads, an output.format outside markdown|plain|json, or an unknown logging.level now fails validation instead of being ignored.

### Bug Fixes

* make the CLI, config and agent do what the documentation says ([#19](https://github.com/bedrock-python/mattermind/issues/19)) ([55aa22d](https://github.com/bedrock-python/mattermind/commit/55aa22db6c62610bc2d96ec1b80b6ea07934f04b))


### Documentation

* an upgrade note for strict configuration validation ([#21](https://github.com/bedrock-python/mattermind/issues/21)) ([0eaba2f](https://github.com/bedrock-python/mattermind/commit/0eaba2fcb083b60500415fee7db85eb2454c4b75))

## [0.1.1](https://github.com/bedrock-python/mattermind/compare/mattermind-v0.1.0...mattermind-v0.1.1) (2026-09-05)


### Bug Fixes

* remove __future__ annotations to fix Typer runtime type resolution ([b30d6ae](https://github.com/bedrock-python/mattermind/commit/b30d6aeb18be0dd53d1793ca71f05a15ee9b0d15))
* update publish workflow, release-please version search, gitignore ([#5](https://github.com/bedrock-python/mattermind/issues/5)) ([ddd00bd](https://github.com/bedrock-python/mattermind/commit/ddd00bd96811f233cd4f5b59c95aa37857fc283d))


### Documentation

* fix license badge to Apache 2.0 and add codecov badge ([5cbe022](https://github.com/bedrock-python/mattermind/commit/5cbe0228e1ccff03d222ae162b0b8d2b24e13467))

## 0.1.0 (2026-05-16)


### Features

* initial implementation of mattermind CLI ([ef8f6a6](https://github.com/bedrock-python/mattermind/commit/ef8f6a670c912aa5c268431a92fc0b8b32484622))


### Documentation

* add badges and documentation link to README ([4ceb61b](https://github.com/bedrock-python/mattermind/commit/4ceb61b942abc6aec54b7f499006725b6e32fccc))
