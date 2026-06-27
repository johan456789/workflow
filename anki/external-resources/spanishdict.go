//go:build ignore

package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"strings"
	"time"

	"github.com/PuerkitoBio/goquery"
	"github.com/spf13/pflag"
)

const (
	spanishDictBaseURL = "https://www.spanishdict.com/pronunciation"
	videoURLTemplate   = "https://sd-pronunciation-processed-videos.sdcdns.com/mobile/lang_es_pron_%d_speaker_%d_syllable_all_version_%d.mp4"
	defaultTimeoutSecs = 30
	defaultUserAgent   = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0"
)

// Pronunciation represents a single pronunciation entry from SpanishDict.
type Pronunciation struct {
	ID        int    `json:"id"`
	IPA       string `json:"ipa"`
	ABC       string `json:"abc"`
	SPA       string `json:"spa"`
	Region    string `json:"region"`
	HasVideo  int    `json:"hasVideo"`
	SpeakerID int    `json:"speakerId"`
	Version   int    `json:"version"`
}

// ComponentData is a minimal struct for parsing SD_COMPONENT_DATA.
// We only extract the fields we actually need.
type ComponentData struct {
	PronunciationProps struct {
		Pronunciations []Pronunciation `json:"pronunciations"`
	} `json:"pronunciationProps"`
}

type SpanishDictError struct {
	Op  string
	Err error
}

func (e SpanishDictError) Error() string {
	if e.Err == nil {
		return e.Op
	}
	return fmt.Sprintf("%s: %v", e.Op, e.Err)
}

func (e SpanishDictError) Unwrap() error {
	return e.Err
}

func wrapErr(op string, err error) error {
	if err == nil {
		return nil
	}
	return SpanishDictError{Op: op, Err: err}
}

func fetchPronunciationPage(client *http.Client, query string) (string, error) {
	url := fmt.Sprintf("%s/%s", spanishDictBaseURL, query)

	req, err := http.NewRequest("GET", url, nil)
	if err != nil {
		return "", err
	}
	req.Header.Set("User-Agent", defaultUserAgent)

	resp, err := client.Do(req)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return "", fmt.Errorf("failed to fetch pronunciation page: %d", resp.StatusCode)
	}

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return "", err
	}

	return string(body), nil
}

// extractComponentData searches all <script> tags for SD_COMPONENT_DATA and
// returns the parsed struct. We search ALL script tags rather than relying on
// a specific index because:
//   - SpanishDict's page structure may change, moving the script position
//   - Different pages may have different numbers of scripts before our target
//   - Searching by content ("window.SD_COMPONENT_DATA") is more robust than
//     relying on DOM position which is fragile across site updates
func extractComponentData(html string) (*ComponentData, error) {
	doc, err := goquery.NewDocumentFromReader(strings.NewReader(html))
	if err != nil {
		return nil, err
	}

	var scriptText string

	// Fast path: try the same specific selector as the Python version.
	// Fall back to a full scan if that position doesn't match.
	selectorText := doc.Find("body > script:nth-child(11)").First().Text()
	if strings.Contains(selectorText, "window.SD_COMPONENT_DATA") {
		scriptText = selectorText
	}

	// Search all <script> tags for the one containing SD_COMPONENT_DATA.
	// This is more robust than relying on a specific index because the
	// page structure may change across different queries or site updates.
	doc.Find("script").Each(func(i int, s *goquery.Selection) {
		if scriptText != "" {
			return // Already found
		}
		text := s.Text()
		if strings.Contains(text, "window.SD_COMPONENT_DATA") {
			scriptText = text
		}
	})

	if scriptText == "" {
		return nil, fmt.Errorf("could not find window.SD_COMPONENT_DATA in the page")
	}

	return parseComponentDataScript(scriptText)
}

func parseComponentDataScript(scriptText string) (*ComponentData, error) {
	re := regexp.MustCompile(`window\.SD_COMPONENT_DATA\s*=\s*(\{.*?\});?\s*$`)
	matches := re.FindStringSubmatch(scriptText)
	if len(matches) < 2 {
		return nil, fmt.Errorf("could not parse window.SD_COMPONENT_DATA JSON")
	}

	var data ComponentData
	if err := json.Unmarshal([]byte(matches[1]), &data); err != nil {
		return nil, fmt.Errorf("invalid JSON in SD_COMPONENT_DATA: %v", err)
	}

	return &data, nil
}

func getPronunciations(data *ComponentData) ([]Pronunciation, error) {
	pronunciations := data.PronunciationProps.Pronunciations
	if len(pronunciations) == 0 {
		return nil, fmt.Errorf("no pronunciations found in the page data")
	}
	return pronunciations, nil
}

func selectPronunciation(pronunciations []Pronunciation, region string) (Pronunciation, error) {
	if region == "auto" {
		// Prefer LATAM, fallback to SPAIN
		for _, pron := range pronunciations {
			if pron.Region == "LATAM" {
				return pron, nil
			}
		}
		for _, pron := range pronunciations {
			if pron.Region == "SPAIN" {
				return pron, nil
			}
		}
		// If neither found, return first available
		return pronunciations[0], nil
	}

	// Find specific region
	regionUpper := strings.ToUpper(region)
	for _, pron := range pronunciations {
		if pron.Region == regionUpper {
			return pron, nil
		}
	}

	return Pronunciation{}, fmt.Errorf("no pronunciation found for region: %s", region)
}

func buildVideoURL(pron Pronunciation) string {
	return fmt.Sprintf(videoURLTemplate, pron.ID, pron.SpeakerID, pron.Version)
}

func buildVideoFilename(pron Pronunciation) string {
	return fmt.Sprintf("lang_es_pron_%d_speaker_%d_syllable_all_version_%d",
		pron.ID, pron.SpeakerID, pron.Version)
}

func downloadVideo(client *http.Client, url string) ([]byte, error) {
	req, err := http.NewRequest("GET", url, nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("User-Agent", defaultUserAgent)

	resp, err := client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("failed to download video: %d", resp.StatusCode)
	}

	return io.ReadAll(resp.Body)
}

func extractAudioToMP3(videoBytes []byte, outputPath string) error {
	// Create temp file for video
	tmpFile, err := os.CreateTemp("", "spanishdict-*.mp4")
	if err != nil {
		return err
	}
	tmpPath := tmpFile.Name()
	defer os.Remove(tmpPath)

	if _, err := tmpFile.Write(videoBytes); err != nil {
		tmpFile.Close()
		return err
	}
	tmpFile.Close()

	// Run ffmpeg to extract audio, capturing stderr for error reporting
	var stderr bytes.Buffer
	cmd := exec.Command("ffmpeg",
		"-i", tmpPath,
		"-acodec", "libmp3lame",
		"-ac", "2",
		"-ar", "44100",
		"-y",
		outputPath,
	)
	cmd.Stderr = &stderr

	if err := cmd.Run(); err != nil {
		// Include ffmpeg's stderr output for debugging
		return fmt.Errorf("ffmpeg failed: %v\nstderr: %s", err, stderr.String())
	}
	return nil
}

func run() error {
	// Define flags using pflag
	region := pflag.String("region", "auto", "Region for pronunciation: auto, latam, or spain")
	outputDir := pflag.String("output-dir", ".", "Directory to save the output MP3 file")
	timeout := pflag.Int("timeout", defaultTimeoutSecs, "HTTP request timeout in seconds")
	jsonOutput := pflag.Bool("json", false, "Output pronunciation data as JSON instead of downloading")

	pflag.Usage = func() {
		fmt.Fprintf(os.Stderr, "Usage: spanishdict <query> [flags]\n\nFlags:\n")
		pflag.PrintDefaults()
	}

	pflag.Parse()

	// Get positional argument (query)
	args := pflag.Args()
	if len(args) != 1 {
		pflag.Usage()
		return SpanishDictError{Op: "invalid arguments", Err: fmt.Errorf("expected 1 argument")}
	}
	query := args[0]

	// Validate region
	validRegions := map[string]bool{"auto": true, "latam": true, "spain": true}
	if !validRegions[*region] {
		return SpanishDictError{
			Op:  "invalid region",
			Err: fmt.Errorf("'%s', must be auto, latam, or spain", *region),
		}
	}

	// Create HTTP client with timeout
	client := &http.Client{
		Timeout: time.Duration(*timeout) * time.Second,
	}

	// Fetch and parse the pronunciation page
	html, err := fetchPronunciationPage(client, query)
	if err != nil {
		return wrapErr("fetch pronunciation page", err)
	}

	data, err := extractComponentData(html)
	if err != nil {
		return wrapErr("extract component data", err)
	}

	pronunciations, err := getPronunciations(data)
	if err != nil {
		return wrapErr("get pronunciations", err)
	}

	// If --json flag, output JSON and exit
	if *jsonOutput {
		jsonBytes, err := json.MarshalIndent(pronunciations, "", "  ")
		if err != nil {
			return wrapErr("marshal pronunciations JSON", err)
		}
		fmt.Println(string(jsonBytes))
		return nil
	}

	// Select pronunciation based on region
	pron, err := selectPronunciation(pronunciations, *region)
	if err != nil {
		return wrapErr("select pronunciation", err)
	}

	// Build URLs and filenames
	videoURL := buildVideoURL(pron)
	videoFilename := buildVideoFilename(pron)
	regionLower := strings.ToLower(pron.Region)
	outputFilename := fmt.Sprintf("sd_%s_%s_%s.mp3", regionLower, query, videoFilename)
	outputPath := filepath.Join(*outputDir, outputFilename)

	// Download video and extract audio
	fmt.Fprintf(os.Stderr, "Downloading pronunciation for '%s' (%s)...\n", query, pron.Region)
	videoBytes, err := downloadVideo(client, videoURL)
	if err != nil {
		return wrapErr("download video", err)
	}

	fmt.Fprintf(os.Stderr, "Extracting audio to %s...\n", outputPath)
	if err := extractAudioToMP3(videoBytes, outputPath); err != nil {
		return wrapErr("extract audio", err)
	}

	fmt.Println(outputPath)
	return nil
}

func main() {
	if err := run(); err != nil {
		fmt.Fprintf(os.Stderr, "error: %v\n", err)
		os.Exit(1)
	}
}
