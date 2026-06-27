# Pronunciation

This documents where to download pronunciations. When downloading audio files, default to saving mp3 file to `/tmp` folder.

Before running any of the commands below, make sure you're in the `external-resources/` directory relative to this workflow.

## All Languages

### Forvo

This provides human recordings of words and phrases. By default, use `corporate` endpoint.

```sh
uv run --env-file ".env.pronunciation" forvo.py \
       --endpoint corporate \
        --text <text> \
        --language <language_tag> \
        --output /tmp/filename.mp3
```

### TTS

The filename format is: `tts_{tts_provider}_{language_tag}_{text_clipped_to_a_few_words}.mp3`

If the TTS support variable speed, use speed 1.0 by default but use speed 0.8 for Spanish.

#### ElevenLabs

This is the most natural sounding tts.
English TTS voice ID: `cgSgspJ2msm6clMCkdW9`.
Spanish TTS voice ID: use the script default (`JBFqnCBsd6RMkjVDRZzb`).

```sh
uv run --env-file ".env.pronunciation" elevenlabs.py \
       --text "<text>" \
       --voice-id "<voice_id>" \
       --speed "<speed>" \
       --output /tmp/filename.mp3
```

#### Google translate

This is not the most natural sounding tts but can be useful as a fallback.

```sh
uvx --from gtts gtts-cli -l <ietf_lang_tag> "<text>" --output /tmp/filename.mp3
```

#### Cartesia

Currenlty the `.go` script only supports Spanish and streaming. This is for interactive use only. Do not use this through ssh.

```sh
echo "<text>" | dotenvx run --quiet -f .env.pronunciation -- go run cartesia.go | ffplay -autoexit -v quiet -nostats -f s16le -ar 44100 -af "aformat=channel_layouts=mono" -
```

## Spanish

### SpanishDict

This is a GET endpoint that provides high-quality human recordings of mostly words (some phrases available).

#### Scrape Audio API

Scrapes pronunciation videos from SpanishDict and extracts audio to mp3. Supports LATAM and SPAIN regional variants.

**Go version:**

```sh
./spanishdict <query> [--region auto|latam|spain] [--output-dir /tmp]
```

If it's not built, build it with:

```sh
go build -ldflags="-s -w" -o spanishdict spanishdict.go
```

**Python version:**

```sh
uv run spanishdict.py <query> [--region auto|latam|spain] [--output-dir /tmp]
```

Output filename format: `sd_{region}_{query}_{original_filename}.mp3`

#### Fallback Audio API

This endpoint is not as good as the previous one. So only use it as a fallback.

```url
https://audio1.spanishdict.com/audio?lang=es&text={word}
```
