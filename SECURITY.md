# Security

Please report vulnerabilities privately through GitHub's "Report a vulnerability" button on this
repository rather than in a public issue. Include what is affected and how to reproduce it.

Shoal handles bot tokens and, with the IPC layer, a shared secret between processes:

- `Token` never shows its secret in `repr`.
- Session files written by `FileSessionStore` contain session IDs that, with the token, can resume a
  session. Keep their directory private to the bot's user.
- The IPC token is compared in constant time. Across hosts, use the `ssl` option.
