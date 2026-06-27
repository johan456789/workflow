# Video

Always convert video files to webm format to have the best compability across all anki clients on different platforms. Use `ffmpeg` to do so.

```sh
ffmpeg -i input.mp4 -c:v libvpx-vp9 -crf 32 -b:v 0 -c:a libopus -b:a 128k output.webm
```

And the format to embed a video in an anki card is:

```html
<video width="100%" src="filename.webm" controls="" controlslist="nodownload"></video>
```

## PlayPhrase.me

This is a great source of clips from movies and tv shows.

TODO: create script for https://www.playphrase.me/