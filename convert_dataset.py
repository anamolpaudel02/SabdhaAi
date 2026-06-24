"""
convert_dataset.py
==================
Translates the English Twitter Hate Speech Dataset (labeled_data.csv)
into Nepali Devanagari and Romanized Nepali forms using Gemini 1.5 Flash.

Main Features:
1. Contextual translation to adapt English slang (hoe, bitch, nigga) to natural Nepali equivalents.
2. Incremental saving: if interrupted, it resumes from the last completed row.
3. Thread-safe concurrent translation workers.
4. Automatic HTML unescaping of raw tweets.
5. Zero external dependencies other than 'google-genai'.

Run:
    python convert_dataset.py --limit 50
"""

import os
import sys
import csv
import json
import time
import html
import pickle
import argparse
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

# Threading Lock for safe writing to CSV
write_lock = threading.Lock()

# System instruction for Gemini API
SYSTEM_INSTRUCTION = (
    "You are a professional linguistic translator and annotator specializing in Nepali language and safety moderation.\n"
    "Your task is to translate and culturally adapt a batch of English tweets containing safety-moderated text into Nepali.\n"
    "Translate each tweet into:\n"
    "1. Devanagari script (natural, spoken, and context-appropriate Nepali).\n"
    "2. Romanized script (how a Nepali speaker would type it phonetically using English/Latin alphabets).\n\n"
    "CRITICAL RULES:\n"
    "- If the original tweet contains offensive language (slang, swearing, general rudeness), translate it into equivalent natural Nepali offensive/vulgar words (e.g. using terms like 'saala', 'randi', 'aama chikne', 'chakka', or other appropriate terms) rather than polite words, to preserve the safety labels (class 1).\n"
    "- If the original tweet contains hateful language (targeted harassment, racism, threats, casteist/religious slangs), adapt it into appropriate targeted hate speech in Nepali (class 0) that matches the intensity.\n"
    "- If the original tweet is normal/neutral, translate it into clean, safe, and polite Nepali (class 2).\n"
    "- Preserve the original tweet's emojis, mentions (@username), and hashtags (#topic) in the translation where appropriate.\n"
    "- Return the translations in a JSON format matching the schema requested below. Do NOT include any explanations or extra text."
)


def clean_json_response(text: str) -> list:
    """Strips markdown wrap syntax if present and parses JSON."""
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()
    return json.loads(text)


def translate_batch_with_retry(client, prompt: str, retries: int = 5, initial_delay: float = 2.0) -> list:
    """Call Gemini API with retry and exponential backoff on rate limits."""
    delay = initial_delay
    for attempt in range(retries):
        try:
            response = client.models.generate_content(
                model="gemini-1.5-flash",
                contents=prompt,
                config={
                    "response_mime_type": "application/json",
                    "system_instruction": SYSTEM_INSTRUCTION,
                }
            )
            if not response.text:
                raise ValueError("Received empty response from Gemini API.")
            return clean_json_response(response.text)
        except Exception as e:
            err_str = str(e)
            is_rate_limit = any(term in err_str for term in ["429", "ResourceExhausted", "Quota exceeded", "exhausted"])
            if is_rate_limit:
                print(f"      [Rate Limit] Attempt {attempt+1}/{retries} failed. Retrying in {delay:.1f}s...")
                time.sleep(delay)
                delay *= 2.0
            else:
                print(f"      [Error] Attempt {attempt+1}/{retries} failed: {e}")
                time.sleep(delay)
                delay *= 1.5
    raise RuntimeError(f"Failed to translate batch after {retries} attempts.")


def process_batch(client, batch: list) -> list:
    """Format prompt, make API request, and return mapped results."""
    # Prepare simplified list for prompt
    input_data = [{"id": item["index"], "text": item["clean_tweet"]} for item in batch]
    prompt = (
        "Translate the following list of English tweets into Nepali (Devanagari and Romanized forms) following the rules.\n"
        "Output ONLY a JSON array of objects with the exact schema:\n"
        '[\n  {"id": integer, "devanagari": "string", "romanized": "string"}\n]\n\n'
        f"Input Tweets:\n{json.dumps(input_data, ensure_ascii=False, indent=2)}"
    )

    try:
        translated_items = translate_batch_with_retry(client, prompt)
        
        # Map responses back to original batch structures
        lookup = {item["id"]: item for item in translated_items if isinstance(item, dict) and "id" in item}
        results = []
        for orig in batch:
            idx = orig["index"]
            match = lookup.get(idx)
            
            dev = match.get("devanagari", "") if match else ""
            rom = match.get("romanized", "") if match else ""
            
            # Fallback if translation is empty
            if not dev:
                dev = "[Translation Error]"
            if not rom:
                rom = "[Translation Error]"

            results.append({
                **orig,
                "tweet_devanagari": dev,
                "tweet_romanized": rom
            })
        return results
    except Exception as e:
        print(f"    [Batch Error] Failed to process batch of size {len(batch)}: {e}")
        # Return batch with error fallbacks
        for orig in batch:
            orig["tweet_devanagari"] = "[Failed]"
            orig["tweet_romanized"] = "[Failed]"
        return batch


def save_pickle_output(csv_path: str, pickle_path: str):
    """Saves the final translated CSV output to a pickle file."""
    print(f"\n[Pickle] Exporting translated dataset to {pickle_path}...")
    try:
        translated_rows = []
        with open(csv_path, "r", newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                translated_rows.append(row)
        with open(pickle_path, "wb") as f:
            pickle.dump(translated_rows, f)
        print("  ✓ Pickle file successfully created!")
    except Exception as e:
        print(f"  [Warning] Failed to write pickle file: {e}")


def main():
    parser = argparse.ArgumentParser(description="Translate English Hate Speech dataset to Nepali.")
    parser.add_argument("--csv-input", default=r"C:\Users\DELL\Downloads\labeled_data.csv", help="Input CSV file path")
    parser.add_argument("--csv-output", default=r"C:\Users\DELL\Downloads\labeled_data_nepali.csv", help="Output CSV file path")
    parser.add_argument("--pickle-output", default=r"C:\Users\DELL\Downloads\labeled_data_nepali.p", help="Output pickle file path")
    parser.add_argument("--batch-size", type=int, default=15, help="Number of tweets per batch")
    parser.add_argument("--workers", type=int, default=4, help="Number of parallel request threads")
    parser.add_argument("--limit", type=int, default=None, help="Stop translating after N rows")
    parser.add_argument("--api-key", default=None, help="Gemini API Key (otherwise uses GEMINI_API_KEY environment variable)")
    args = parser.parse_args()

    # Verify Gemini Client
    api_key = args.api_key or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("\n[Error] Gemini API key not found!")
        print("Please set the GEMINI_API_KEY environment variable or pass it with --api-key.")
        print("Example: $env:GEMINI_API_KEY=\"AIzaSy...\"")
        sys.exit(1)

    try:
        from google import genai
        client = genai.Client(api_key=api_key)
    except ImportError:
        print("\n[Error] google-genai package is not installed.")
        print("Please run: pip install google-genai")
        sys.exit(1)

    # 1. Check Input Files
    if not os.path.exists(args.csv_input):
        print(f"\n[Error] Input file '{args.csv_input}' does not exist.")
        sys.exit(1)

    print(f"\n[Setup] Loading source dataset: {args.csv_input}")
    raw_tweets = []
    with open(args.csv_input, "r", newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        for idx, row in enumerate(reader):
            if not row:
                continue
            # Format: ,count,hate_speech,offensive_language,neither,class,tweet
            # Some CSV rows may be corrupted, so we handle missing items safely
            tweet_index = int(row[0]) if row[0] else idx
            count = int(row[1]) if len(row) > 1 else 0
            hs = int(row[2]) if len(row) > 2 else 0
            ol = int(row[3]) if len(row) > 3 else 0
            ne = int(row[4]) if len(row) > 4 else 0
            cls = int(row[5]) if len(row) > 5 else 2
            tweet_text = row[6] if len(row) > 6 else ""
            
            raw_tweets.append({
                "index": tweet_index,
                "count": count,
                "hate_speech": hs,
                "offensive_language": ol,
                "neither": ne,
                "class": cls,
                "clean_tweet": html.unescape(tweet_text)
            })

    # Apply Limit if specified
    if args.limit is not None:
        raw_tweets = raw_tweets[:args.limit]
        print(f"[Setup] Limit applied: processing first {args.limit} rows.")

    total_tweets = len(raw_tweets)
    print(f"[Setup] Total rows loaded: {total_tweets:,}")

    # 2. Check Resumption
    translated_ids = set()
    if os.path.exists(args.csv_output):
        try:
            with open(args.csv_output, "r", newline="", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get("index"):
                        translated_ids.add(int(row["index"]))
            print(f"[Setup] Found existing progress: {len(translated_ids):,} rows already translated.")
        except Exception as e:
            print(f"[Setup] Warning reading existing file for progress check: {e}")

    # Filter tweets to only translate missing ones
    pending_tweets = [t for t in raw_tweets if t["index"] not in translated_ids]
    already_done = total_tweets - len(pending_tweets)

    if not pending_tweets:
        print("[Setup] All items are already translated. Done!")
        if not os.path.exists(args.pickle_output):
            save_pickle_output(args.csv_output, args.pickle_output)
        return

    print(f"[Setup] Remaining rows to translate: {len(pending_tweets):,}")

    # Initialize CSV header if new file
    if not os.path.exists(args.csv_output):
        with open(args.csv_output, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow([
                "index", "count", "hate_speech", "offensive_language",
                "neither", "class", "original_tweet", "tweet_devanagari", "tweet_romanized"
            ])

    # 3. Create Batches
    batches = []
    current_batch = []
    for item in pending_tweets:
        current_batch.append(item)
        if len(current_batch) == args.batch_size:
            batches.append(current_batch)
            current_batch = []
    if current_batch:
        batches.append(current_batch)

    # 4. Translation Run
    print(f"\n[Execution] Starting translation using {args.workers} concurrent workers...")
    print(f"[Execution] Batches: {len(batches):,} (Batch Size: {args.batch_size})")
    
    start_time = time.time()
    completed_count = already_done

    def worker_job(batch_items):
        nonlocal completed_count
        results = process_batch(client, batch_items)
        
        # Thread-safe append to CSV
        with write_lock:
            with open(args.csv_output, "a", newline="", encoding="utf-8-sig") as csv_file:
                writer = csv.writer(csv_file)
                for r in results:
                    writer.writerow([
                        r["index"], r["count"], r["hate_speech"], r["offensive_language"],
                        r["neither"], r["class"], r["clean_tweet"], r["tweet_devanagari"], r["tweet_romanized"]
                    ])
            completed_count += len(results)
            pct = (completed_count / total_tweets) * 100
            elapsed = time.time() - start_time
            rate = (completed_count - already_done) / elapsed if elapsed > 0 else 0
            eta = (total_tweets - completed_count) / rate if rate > 0 else 0
            
            # Print status
            sys.stdout.write(
                f"\r    Progress: {completed_count:,}/{total_tweets:,} ({pct:.2f}%) | "
                f"Rate: {rate:.1f} rows/s | ETA: {eta/60:.1f} mins    "
            )
            sys.stdout.flush()

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = [executor.submit(worker_job, b) for b in batches]
        for fut in as_completed(futures):
            try:
                fut.result()
            except Exception as e:
                print(f"\n    [Worker Error] Thread execution failed: {e}")

    # 5. Export to Pickle
    save_pickle_output(args.csv_output, args.pickle_output)

    total_time = time.time() - start_time
    print(f"\n\n[Finished] Dataset translation complete!")
    print(f"  Total time elapsed : {total_time/60:.2f} minutes")
    print(f"  CSV Output         : {args.csv_output}")
    print(f"  Pickle Output      : {args.pickle_output}")
    print("═" * 55 + "\n")


if __name__ == "__main__":
    main()
