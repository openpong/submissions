# openpong submissions

Entries for the [openpong](https://openpong.ai) robot table-tennis league.

Every bot's weights are encrypted to its league's key before they are committed here. Anyone can see
that an entry exists, who made it and when; only the league can read the weights.

## Enter a bot

1. **Build it against the scene.** Download the open league's scene pack (`ittf-std`) from
   [openpong.ai/compete](https://openpong.ai/compete). Its `README.md` describes the physics, the
   rules, the controller contract and the published network architecture your weights must use.

2. **Check your file** before encrypting it. This is the same admission check the league runs; it
   needs only Python and numpy:

   ```sh
   python3 tools/admit.py mybot.safetensors --league ittf-std
   ```

3. **Encrypt your weights** with [age](https://github.com/FiloSottile/age) (`brew install age`,
   `apt install age`, or a release binary), using the league's public key:

   ```sh
   age -R leagues/ittf-std/recipient.txt -o bot.safetensors.age mybot.safetensors
   ```

4. **Add one folder** named after your bot, inside the league's folder, holding the encrypted file
   and an `entry.json`:

   ```
   entries/ittf-std/spin-doctor/
     bot.safetensors.age
     entry.json
   ```

   ```json
   {
     "name": "spin-doctor",
     "author": "your-github-login",
     "website": "https://example.com",
     "racketColor": "#e34948",
     "equipment": { "mu_front": 0.9, "e_front": 0.89, "mu_back": 1.4, "e_back": 0.85 }
   }
   ```

   `name` and `author` are required. `website`, `racketColor` and `equipment` are optional.

5. **Open a pull request.** Two checks run: one confirms the entry is well formed, the other decrypts
   the weights and runs the admission check on them, reporting only whether they were admitted. Once
   both pass and the pull request is merged, the bot is entered.

## Rules

- One bot per GitHub account in each league. You can replace your own entry with a new pull request
  until the league starts.
- Entries go only into a league whose `leagues/<league>/league.json` says it is open.
- The decrypted file must be a `.safetensors` file in the league's published architecture. If its
  metadata carries a physics fingerprint, it must be the league's (`54fc19f01036` for `ittf-std`). No
  code is ever run from an entry: the league reads the tensors into its own network.
- The encrypted file may be at most 1 MB. A bot in the published architecture is about 100 KB.
- Racket equipment, if declared, must be legal: friction `mu` between 0.5 and 1.5, rebound `e`
  between 0.82 and 0.92, for each face.
- The league runs once five entries are merged. Standings and a fact sheet for every bot are
  published on [openpong.ai](https://openpong.ai).

## Keys

Each league has its own key pair. The public half is `leagues/<league>/recipient.txt`. The private
half is held by the league and by this repository's admission check, and both copies are deleted
once that league's results are published and settled. After that, no one can decrypt that league's
entries again, even though the encrypted files stay in the history. Publish your weights yourself
if you want them public.

## Why encrypted

A public repository gives every entry an identity, a timestamp and a review before anything is run.
Encryption keeps the weights private all the same. Because the encrypted file is in the git history,
an entry also cannot be swapped after the fact without a new commit.
