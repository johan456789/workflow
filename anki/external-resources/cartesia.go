package main

import (
	"bufio"
	"bytes"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"strings"
)

type chunkMsg struct {
	Type string `json:"type"`
	Done bool   `json:"done"`
	Data string `json:"data"` // base64 audio
}

func main() {
	url := "https://api.cartesia.ai/tts/sse"

	transcript, err := readTranscript()
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}

	payloadMap := map[string]any{
		"model_id":   "sonic-3",
		"transcript": transcript,
		"voice": map[string]string{
			"mode": "id",
			"id":   "5c5ad5e7-1020-476b-8b91-fdcbe9cc313c",
		},
		"output_format": map[string]any{
			"container":   "raw",
			"encoding":    "pcm_s16le",
			"sample_rate": 44100,
		},
		"generation_config": map[string]any{
			"volume":  1,
			"speed":   1,
			"emotion": "neutral",
		},
	}
	payload, err := json.Marshal(payloadMap)
	if err != nil {
		fmt.Fprintln(os.Stderr, "json marshal:", err)
		os.Exit(1)
	}

	req, err := http.NewRequest("POST", url, bytes.NewReader(payload))
	if err != nil {
		fmt.Fprintln(os.Stderr, "new request:", err)
		os.Exit(1)
	}

	req.Header.Set("Cartesia-Version", "2025-04-16")
	req.Header.Set("Authorization", "Bearer "+os.Getenv("CARTESIA_API_KEY"))
	req.Header.Set("Content-Type", "application/json")
	// Helps proxies not buffer:
	req.Header.Set("Accept", "text/event-stream")

	res, err := http.DefaultClient.Do(req)
	if err != nil {
		fmt.Fprintln(os.Stderr, "http do:", err)
		os.Exit(1)
	}
	defer res.Body.Close()

	if res.StatusCode < 200 || res.StatusCode >= 300 {
		b, _ := io.ReadAll(res.Body)
		fmt.Fprintf(os.Stderr, "http status %s\n%s\n", res.Status, string(b))
		os.Exit(1)
	}

	sc := bufio.NewScanner(res.Body)
	// SSE lines can be long; increase scanner buffer.
	buf := make([]byte, 0, 1024*64)
	sc.Buffer(buf, 1024*1024*16) // 16MB max line

	out := bufio.NewWriterSize(os.Stdout, 1024*64)
	defer out.Flush()

	for sc.Scan() {
		line := sc.Text()

		// SSE: we only care about "data: ..."
		if !strings.HasPrefix(line, "data:") {
			continue
		}
		dataLine := strings.TrimSpace(strings.TrimPrefix(line, "data:"))

		// Some SSE servers send keepalives like "data: [DONE]" etc.
		if dataLine == "" || dataLine == "[DONE]" {
			continue
		}

		var m chunkMsg
		if err := json.Unmarshal([]byte(dataLine), &m); err != nil {
			// Not JSON? Ignore.
			continue
		}
		if m.Type != "chunk" || m.Data == "" {
			if m.Done {
				break
			}
			continue
		}

		raw, err := base64.StdEncoding.DecodeString(m.Data)
		if err != nil {
			// Sometimes base64 may be URL-safe without padding; try alternate.
			raw2, err2 := base64.RawStdEncoding.DecodeString(m.Data)
			if err2 != nil {
				raw3, err3 := base64.RawURLEncoding.DecodeString(m.Data)
				if err3 != nil {
					fmt.Fprintln(os.Stderr, "base64 decode:", err)
					os.Exit(1)
				}
				raw = raw3
			} else {
				raw = raw2
			}
		}

		if _, err := out.Write(raw); err != nil {
			fmt.Fprintln(os.Stderr, "stdout write:", err)
			os.Exit(1)
		}

		if m.Done {
			break
		}
	}

	if err := sc.Err(); err != nil {
		fmt.Fprintln(os.Stderr, "scan:", err)
		os.Exit(1)
	}
}

func readTranscript() (string, error) {
	if len(os.Args) > 1 {
		return strings.Join(os.Args[1:], " "), nil
	}

	info, err := os.Stdin.Stat()
	if err != nil {
		return "", fmt.Errorf("stdin stat: %w", err)
	}
	if info.Mode()&os.ModeCharDevice == 0 {
		b, err := io.ReadAll(os.Stdin)
		if err != nil {
			return "", fmt.Errorf("stdin read: %w", err)
		}
		s := strings.TrimSpace(string(b))
		if s != "" {
			return s, nil
		}
	}

	return "", fmt.Errorf("missing transcript: pass as arg or pipe via stdin")
}
