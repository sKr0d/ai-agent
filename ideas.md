# TODO


## Github
- [ ] create code owners
  - [ ] sKr0d is code owner
- [ ] add breanch protection rules
  - [ ] code owner review is required before merge to main
  - [ ] tell agent to start using branches and pull requests
    - [ ] branch naames should be short, but descriptive. Either a ticket number or 2-3 words about what the branch is for
  - [ ] figure out how to give the agent proper credentials in GitHub - PAT? SSH KEY?
- [ ] create a pull request reviewer agent to review any findings and report required fixes back to the coordinator to decide if the coding agent needs to fix it or if a human needs to review
  - [ ] provide me with some options. Is there a notification method from GitHub that review agent can subscribe to?  Or is there a mechanism in gh command line utility?  Or do we just need to poll GH every minute?
- [ ] create actions (on merge to main)
  - [ ] run unit tests
  - [ ] build dockerfile
    - [ ] use unix epoch as tag version
  - [ ] scan for vulnerabilities witth trivy
  - [ ] push image to ghithub registry
- [ ] update deployment agent to pull images from ghcr.io 
