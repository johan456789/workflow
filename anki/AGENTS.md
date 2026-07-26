# Anki Workflow

This is the personal Anki flashcard workflow. For API mechanics (request format, helper scripts, action categories), use the `anki-connect` skill.
After `findNotes`/`findCards`, always call `notesInfo`/`cardsInfo` and report card status (new or not).

## Searching vocabulary

When checking whether a Spanish word already exists as a note, always search both the masculine and feminine forms (e.g. `secretario` and `secretaria`). A single note may cover both genders with an `(nm/f)` tag or similar, so searching only one form can return a false negative. Try the singular masculine, singular feminine, and plural variants before concluding the word is missing.

## Inspecting notes

After creating or editing a note, share an inline-code `anki://x-callback-url/browser?search=nid%3A<noteId>` link so the user can open the note in the Anki desktop/browser UI with one click. For example: `anki://x-callback-url/browser?search=nid%3A1784894070493`. Always use inline code for the URL — do NOT use markdown hyperlink syntax like `[label](anki://...)`, because Discord does not render `anki://` links clickably.

After every note edit or media upload, call the AnkiConnect `sync` action so the changes are pushed to AnkiWeb and other devices.

## Deck names

Always check the latest deck names by listing them before adding a new note — parent decks may change (the wildcard part). The user often uses short names:

### Spanish

| Short name | Full deck name |
|---|---|
| spanish deck | `*::_Languages::_Spanish🇪🇸` |
| spanish daily deck | `*::_Languages::_Spanish🇪🇸::Daily life` |
| spanish daily listening deck | `_tmp container::_Languages::_Spanish🇪🇸::Daily life::Listening` |

### English

| Short name | Full deck name |
|---|---|
| english deck | `*::_Languages::English🇺🇸` |
| english daily deck | `*::_Languages::English🇺🇸::Daily life` |

## Note formatting

Anki does **not** render Markdown in note fields. Use HTML for all formatting (e.g. `<br>` for line breaks, `<em><strong>...</strong></em>` for bold + italic, `<ul><li>...</li></ul>` for lists, `<a href="...">...</a>` for links). Markdown like `**bold**`, `*italic*`, `[text](url)`, or `- list item` will appear as raw text on the card.

### Spanish daily deck cloze (default for new Spanish notes)

- Model: `Cloze`
- Deck: spanish daily deck
- Text field format: Spanish sentence, then English translation on the next line using `<br>`
  - Add an image (see [Adding images](#adding-images)) after the sentences if the word is any of:
    - Concrete nouns
    - Action verbs with a distinctive visual (good: run, jump, kneel, hug, pour, cut, throw, whisper. bad: get, make, take, put, do)
    - Adjectives with strong visual properties
    - Prepositions and spatial relations (e.g. under, between, behind, next to)
  - Make sure there's a `<br>` between the last sentence and the image
- Cloze only the Spanish target word; do NOT cloze the English translation
- Bold + italicize the target word in both sentences with `<em><strong>...</strong></em>`
- Extra field: add SpanishDict pronunciation audio (see [adding pronunciation](#adding-pronunciation))
  - Field order: pronunciation audio, then helper notes
  - Put a `<br>` between the pronunciation audio and helper notes

Example:

```
El perro mueve la {{c1::<em><strong>cola</strong></em>}}.<br>
The dog wags its <em><strong>tail</strong></em>.
```

### Spanish daily listening deck cloze

The user might say "create a listening note for `<sentences>`" to request this note type.
The sentence might include `{}`. The text inside `{}` is the target part to cloze.
If the user doesn't include `{}`, assume the whole sentence is the target part to cloze.

- Deck: spanish daily listening deck
- Model: `Cloze`
- Text field format: Spanish sentence, then on the next line add TTS audio of the Spanish sentence (see [adding pronunciation](#adding-pronunciation)). Make sure there's a `<br>` between the sentence and the audio
- Extra field: English translation of the sentence
- Cloze only the Spanish target part (word, phrase, or whole sentence); do NOT cloze the English translation
- Bold + italicize the target word in both sentences with `<em><strong>...</strong></em>`

### English daily deck cloze

- Deck: english daily deck
- Model: `Cloze`
- Text field format:
  - Line 1: sentence with target word clozed as `{{c1::<em><strong>target</strong></em>}}`
  - Line 2: blank line (`<br><br>`)
  - Line 3: definition line: `Meaning: {{c2::concise definition}}`
- Extra field: leave empty unless specified
  - Field order: pronunciation audio, then image, then helper notes
  - Put a `<br>` between the pronunciation audio and the image

## Example sentences (Spanish)

When adding example sentences to a note, follow these instructions:

<instructions>
I am a beginner learning Spanish and want to understand basic grammar and vocabulary. Please explain the word and concept in simple terms (NOT one-word translation), and provide example sentences. Focus on one word or grammar point at a time, and give multiple simple examples (use A1 words) in increasing difficulty order. If I have questions about why something is used in a specific way, please provide clear explanations. If I need help with conjugation, prepositions, or pronouns, walk me through how they work with simple examples. Also, gradually introduce slightly more complex examples as I understand each concept.

Try to use a variety of simple forms of the same word in the example sentences, e.g. single/plural, masculine/feminine, infinitive, present 1st/2nd/3rd person single/plural.
Some example input words and the forms you should consider using in example sentences:

- novio: novio, novia, novios, novias.
- sentir: sentir, siento, sientes, siente, sentimos, sentís, sienten

You should NOT try to use all of them in examples. Just pick a few. The main focus of examples is showing the usage of the word in different contexts and in increasing difficulty. It is NOT to show how to use the word in different forms.

When I ask about a word or phrase, you should include a short and simple etymology if it helps me remember it. You should also bold AND italicize the word in the example sentences. Always remember to do both. Other words in the sentence should be regular, i.e. NOT bold nor italicized. Both the original Spanish sentence and the translated English sentence should follow the same rule. The example sentences should be numbered. To make it easy for me to copy and paste, you should NOT put the example sentences in bullet/numbered lists. Take the word "book" in the example sentence "I like books".

Your output in markdown would be:

<output>
1.
Me gustan los ***libros***.
I like ***books***.
2.
Compré tres ***libros***.
I bought three ***books***.
</output>

NOTE: The number should NOT be on the same line as the examples. All example sentences have their own lines.

If the user follows up with numbers, it means they want you to put those examples specified by the numbers in a code block for easy copy, and make sure to group by language. Take the above examples:

User: 1,2

Response:

<output>
Spanish:

```html
Me gustan los <em><strong>libros</strong></em>.<br>
Compré tres <em><strong>libros</strong></em>.
```

English

```html
I like <em><strong>books</strong></em>.<br>
I bought three <em><strong>books</strong></em>.
```

</output>

NOTE: each example should be separated by `<br>` if there is more than one.

You should prefer showing the correct usage. If showing incorrect usage is necessary to make a point, make sure to strike out the sentence to avoid confusion.

Your response should always be in English unless otherwise explicitly specified.

</instructions>

## Adding pronunciation

Refer to [external-resources/pronunciation.md](external-resources/pronunciation.md) for available sources and commands.

- **Spanish vocabulary**: use SpanishDict (human pronunciation, LATAM preferred)
- **Spanish grammar/sentences**: use ElevenLabs TTS (speed 0.8 for Spanish, 1.0 for English)
- **English**: refer to the English voice ID in pronunciation.md

## Adding images

Refer to [external-resources/image.md](external-resources/image.md) for sources and commands.

Prioritize Pexels. Download multiple images at a time to reduce request approvals. Pick the best image based on how well the main subject complements the note.

## Adding videos

Refer to [external-resources/video.md](external-resources/video.md) for formats and sources.

## Starting Anki from terminal

If Anki is not running and the AnkiConnect server is unavailable, you can launch Anki from the terminal.

### macOS

```bash
open -a Anki
```

If Anki is not in `/Applications/`, find it with: `mdfind "kMDItemKind == 'Application'" | grep -i anki`

### Linux

```bash
anki
```

### Windows (Command Prompt / PowerShell)

```cmd
"C:\Program Files\Anki\anki.exe"
```

If the above path doesn't work, check `C:\Users\<username>\AppData\Local\Programs\Anki\anki.exe` or search for `anki.exe`.
