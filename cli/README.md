# METRON bootstrap CLI

This package is the bootstrap helper for the METRON plugin. The canonical plugin, skills, runtime, and financial logic remain in [riyannode/metronarc](https://github.com/riyannode/metronarc).

Run:

```sh
npx @riyannode/metron
```

Available commands:

- `metron`
- `metron setup`
- `metron doctor`
- `metron --help`
- `metron --version`

The setup command registers the METRON GitHub marketplace at `master` and prints the remaining ChatGPT desktop plugin-installation steps. It does not silently install or enable the ChatGPT plugin.

This bootstrap does not log in to Circle, accept Circle Terms, access wallets, execute payments, or initialize financial state.
