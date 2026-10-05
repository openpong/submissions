# openpong submissions

Entries for the [openpong](https://openpong.ai) robot table-tennis league.

Every bot's weights are encrypted to the league's key before they are committed here. Anyone can
see that an entry exists, who made it and when; only the league's evaluator can read the weights.

## Enter a bot

1. **Build it against the scene.** Download the open league's scene pack (`ittf-std`) from
   [openpong.ai/compete](https://openpong.ai/compete). Its `README.md` describes the physics, the
   rules, the controller contract and the published network architecture your weights must use.

2. **Encrypt your weights** with [age](https://github.com/FiloSottile/age) (`brew install age`,
   `apt install age`, or a release binary), using the league's public key in `recipient.txt`:

   ```sh
   age -R recipient.txt -o bot.safetensors.age mybot.safetensors
   ```

3. **Add one folder** named after your bot, holding the encrypted file and an `entry.json`:

   ```
   entries/spin-doctor/
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

4. **Open a pull request.** A check confirms the entry is well formed. Once it is merged, the bot
   is entered.

## Rules

- One bot per GitHub account. You can replace your own entry with a new pull request until the
  league starts.
- The decrypted file must be a `.safetensors` file in the league's published architecture, with
  the league's physics fingerprint (`54fc19f01036` for `ittf-std`) in its metadata. Anything else is
  refused before it plays. No code is ever run from an entry: the evaluator reads the tensors into
  its own network.
- The encrypted file may be at most 1 MB. A bot in the published architecture is about 100 KB.
- Racket equipment, if declared, must be legal: friction `mu` between 0.5 and 1.5, rebound `e`
  between 0.82 and 0.92, for each face.
- The league runs once five entries are merged. Standings and a fact sheet for every bot are
  published on [openpong.ai](https://openpong.ai). Weights stay encrypted here; publish yours
  yourself if you want to.

## Why encrypted

A public repository gives every entry an identity, a timestamp and a review before anything is
run. Encryption keeps the weights private all the same. Because the encrypted file is in the git
history, an entry also cannot be swapped after the fact without a new commit.
