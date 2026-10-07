# METRON bootstrap CLI

This package is a small setup helper for the METRON plugin. The canonical plugin, skills, and runtime remain in [riyannode/metronarc](https://github.com/riyannode/metronarc).

The package is prepared for npm publication and is not published yet. After publication, the intended command is:

```sh
npx @riyannode/metron
```

The command registers the `riyannode/metronarc` GitHub marketplace at `master` and prints the steps to install METRON in ChatGPT desktop. It does not install or enable the plugin automatically.

## Commands

- `metron` or `metron setup` checks prerequisites, registers the marketplace if needed, verifies it, and prints next steps.
- `metron doctor` reports local prerequisites and marketplace status without changing files or configuration.
- `metron --help` shows command usage.
- `metron --version` shows the package version.

Circle CLI detection is informational. This bootstrap never logs in to Circle, accepts Terms, accesses wallets, or performs financial actions.
