---
description: Add vocabulary to the biasing list and verify it reaches the decoder
argument-hint: <phrase to bias towards>
---

Add this to the hotword list: $ARGUMENTS

1. Read `config/hotwords.txt` and its header comment first — it documents the
   format and the three ways biasing silently does nothing.
2. Add the phrase. Prefer the **multi-word phrase** over its individual words: a
   phrase accumulates boost across the sequence and only fires when the words
   appear together, which is both stronger and safer. Give it a score only if it
   needs to differ from the global default.
3. Check you have not diluted the graph: if a similar phrase is already there,
   extend it rather than adding a near-duplicate. A phrase that never fires
   should be deleted, not kept "just in case".
4. Verify it reaches the decoder:

   ```
   ./build/bin/vcc_cli.exe --show-hotwords
   ```

   The phrase must appear, uppercased, with a score. If the output says biasing
   is INACTIVE, report the blocker rather than assuming it worked.
5. If a corpus exists, re-run `/eval` and report whether the addition moved WER.
   If it did not, say so — an unverified hotword is a guess.

Do not add the phrase to `config/rewrites.txt` instead. Fixing it in the decoder
generalises to nearby phrasings; a text rewrite does not.
