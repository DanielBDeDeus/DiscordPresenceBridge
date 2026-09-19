# Discord Social SDK vendor directory

Do not commit proprietary Discord SDK binaries here unless Discord's license explicitly
allows redistribution.

When the official SDK archive is obtained, unpack/copy the required native headers and
libraries here and implement the wrapper in:

```text
native/discord_social_sdk/
```

The rest of the application must interact with that wrapper only through the existing
Discord backend interface.
