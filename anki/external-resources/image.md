# Image

This documents where to download images. When downloading image files, default to saving files to `/tmp` folder. The naming convention should be `<title>_<source>[_<photographer>].<ext>`.

Before running any of the commands below, make sure you're in the `external-resources/` directory relative to this workflow.

To evaluate which image is the best for a task, read the images yourself if you are multimodal. Otherwise use the opencode **eyes** subagent (it can read and describe images); fall back to `codex exec` only if the eyes subagent is unavailable. Apply this checklist, in order: (1) horizontal/landscape orientation, (2) target subject front and center, filling the frame, (3) single subject on a plain background — no clutter, props, or styled-photography setups, (4) no people or faces unless the word is an action verb that needs a human demonstrating it, (5) no watermarks or text overlays, (6) usable license — Pexels, Pixabay, Unsplash, or Wikimedia Commons only; reject Dreamstime/Getty/iStock previews.

Eyes subagent example:

```sh
# (opencode: launch the eyes subagent with a prompt listing the image paths
#  and asking which single image best facilitates learning)
```

Codex fallback example:

```sh
echo 'these are photos for a spanish note "for here or to go" "Para aquí o para llevar", which image do you think is best to add to the note to facillate learning?'  | codex exec -i pexels_*.jpg
```

Prioritize using Brave Search as the source. Fall back to Pexels if Brave is unavailable or returns no usable results.

## Wikipedia

```url
https://commons.wikimedia.org/w/api.php?action=query&generator=search&gsrsearch={query}&gsrnamespace=6&prop=imageinfo&iiprop=url&format=json
```

The JSONPath for the image urls is:

```jsonpath
$.query.pages.*.imageinfo[*].url
```

## Brave Search

<https://api-dashboard.search.brave.com/api-reference/images/image_search>
Authentication via `X-Subscription-Token` header. Free tier is rate-limited to 1 query/sec; paid plans higher.

### [Search images](https://api-dashboard.search.brave.com/api-reference/images/image_search)

Required: `q` (query, up to 400 chars / 50 words). Optional: `count` (1-200, default 50), `safesearch` (`off`|`strict`, default `strict`), `search_lang`, `country`, `spellcheck`.

```sh
dotenvx run -f ".env.image" -- sh -c 'curl -s --compressed -H "Accept: application/json" -H "X-Subscription-Token: $BRAVE_SEARCH_API_KEY" "https://api.search.brave.com/res/v1/images/search?q={query}&count=5&safesearch=strict"'
```

Note: do NOT send `Accept-Encoding: gzip` without curl's `--compressed` flag, or the response comes back as gzipped binary.

The JSONPath for the direct image urls is:

```jsonpath
$.results[*].properties.url
```

Each result also has `url` (the source page, not the image) and `thumbnail.url`. Use `.properties.url` for the actual image file.

## Pexels

<https://www.pexels.com/api/documentation/#guidelines>
Whenever you are doing an API request, make sure to show a **prominent link to Pexels**. You can use a text link (e.g. "Photos provided by Pexels") or a link with our logo. By default, the API is rate-limited to 200 requests per hour and 20,000 requests per month.

### [Search a photo](https://www.pexels.com/api/documentation/#photos-search)

The current supported locales are: `en-US`, `pt-BR`, `es-ES`, `ca-ES`, `de-DE`, `it-IT`, `fr-FR`, `sv-SE`, `id-ID`, `pl-PL`, `ja-JP`, `zh-TW`, `zh-CN`, `ko-KR`, `th-TH`, `nl-NL`, `hu-HU`, `vi-VN`, `cs-CZ`, `da-DK`, `fi-FI`, `uk-UA`, `el-GR`, `ro-RO`, `nb-NO`, `sk-SK`, `tr-TR`, `ru-RU`. It's an optional parameter.

```sh
dotenvx run -f ".env.image" -- sh -c 'curl -v -H "Authorization: $PEXELS_API_KEY" "https://api.pexels.com/v1/search?query={query}&per_page=5&locale={locale}"'
```

The JSONPath for the image urls is:

```jsonpath
$.photos.*.src.medium
```

Photos are available in sizes: ‎`original`, `large2x`, `large`, `medium`, `small`, `portrait`, `landscape`, `tiny`. Usually the medium-size image is enough for Anki notes.

## Unslpash

<https://unsplash.com/documentation>
Demo apps are limited to **50 requests** per hour. Currently, there's limited non-english query support.

### [Search photos](https://unsplash.com/documentation#search-photos)

```sh
dotenvx run -f ".env.image" -- sh -c 'curl -H "Authorization: Client-ID $UNSPLASH_ACCESS_KEY" "https://api.unsplash.com/search/photos?query={query}&per_page=5"'
```

The JSONPath for the image urls is:

```jsonpath
$.results.*.urls.small
```

Photos are available in `raw`, `full`, `regular`, `small`, `thumb`. Usually the small-size image is enough for Anki notes.

## Pixabay

<https://pixabay.com/api/docs/#>
By default, you can make up to 100 requests per 60 seconds.

### [Search images](https://pixabay.com/api/docs/#)

```sh
dotenvx run -f ".env.image" -- sh -c 'curl "https://pixabay.com/api/?key=$PIXABAY_API_KEY&q={query}&image_type=photo&per_page=5"'
```

The JSONPath for the image urls is:

```jsonpath
$.hits.*.webformatURL
```
