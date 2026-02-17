# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Professional README with comprehensive documentation and badges
- - Standardized issue templates (bug reports and feature requests)
  - - Pull request template with comprehensive guidelines
    - - CHANGELOG for tracking releases and notable changes
     
      - ### Changed
      - - Enhanced project documentation structure
        - - Improved repository metadata and discoverability
         
          - ### Fixed
          - - (pending)
           
            - ## [0.1.0] - 2026-02-16
           
            - ### Added
            - - Initial project structure with core services (gateway, signal, risk, execution)
              - - Real-time market data ingestion from Alpaca (IEX stream)
                - - QuestDB and Redis infrastructure for data persistence
                  - - AI signal generation with hybrid model inference
                    - - Multi-model signal stream (Hybrid AI + SMA crossover + RSI mean-reversion)
                      - - Risk engine scaffolding with kill-switch logic
                        - - Paper trading arena with fake cash and real market prices
                          - - Live model leaderboard for strategy performance tracking
                            - - Next.js dashboard with Socket.IO integration
                              - - Optional live trading execution mode
                                - - Docker Compose support for containerized deployment
                                  - - CI/CD pipeline with GitHub Actions
                                    - - Comprehensive project documentation
                                      - - Code of Conduct and Security Policy
                                        - - Contributing guidelines
                                         
                                          - ### Known Limitations
                                          - - Risk and execution services do not yet consume Redis channels end-to-end
                                            - - Some environment variables are forward-looking and not yet used
                                              - - Service-level integration tests are not yet enforced in CI
                                               
                                                - ---

                                                ## Versioning Strategy

                                                We follow [Semantic Versioning](https://semver.org/) with the following convention:

                                                - **MAJOR**: Breaking changes to the API or system architecture
                                                - - **MINOR**: New features or significant functionality
                                                  - - **PATCH**: Bug fixes and minor improvements
                                                   
                                                    - ## Release Process
                                                   
                                                    - 1. Update CHANGELOG.md with changes since last release
                                                      2. 2. Update version numbers in relevant files
                                                         3. 3. Create a Git tag with the version number
                                                            4. 4. Create a GitHub Release with release notes from CHANGELOG
                                                               5. 5. Publish any artifacts or packages
                                                                 
                                                                  6. ## Commit Message Format
                                                                 
                                                                  7. We use [Conventional Commits](https://www.conventionalcommits.org/) format:
                                                                 
                                                                  8. - `feat:` - New feature
                                                                     - - `fix:` - Bug fix
                                                                       - - `docs:` - Documentation changes
                                                                         - - `style:` - Code style changes (formatting, semicolons, etc.)
                                                                           - - `refactor:` - Code refactoring without feature changes
                                                                             - - `perf:` - Performance improvements
                                                                               - - `test:` - Test additions or updates
                                                                                 - - `chore:` - Build, CI, or dependency updates
                                                                                   - - `ci:` - CI/CD configuration changes
                                                                                     - - `revert:` - Reverting a previous commit
                                                                                       - 
