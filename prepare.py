#!/usr/bin/env python3

"""Download a TNGO labeling session and extract its video frames."""

import os
import sys
import argparse
import tempfile
from pathlib import Path
import cv2
import multiprocessing
from dotenv import load_dotenv
from tqdm import tqdm

# Prefer the bundled API in both the main process and spawned download workers.
sys.path.insert(0, str(Path(__file__).resolve().parent / "lib/tngo-api-python/src"))

def get_session_details(api, target_session_id):
    """Resolve a public/proxy session ID to its session-library record."""
    tqdm.write(f"Looking up session details for '{target_session_id}'...")

    for session in api.sessions.all(page_size=100):
        if session.details and session.details.session_id == target_session_id:
            tqdm.write(f"Match found! Internal ID: {session.id}")
            return session

    return None

def frame_offsets(chunks, metadata):
    """Index every session chunk before filtering or downloading videos."""
    offsets = {}
    counts = {}
    next_index = 0
    for chunk in sorted(chunks, key=lambda chunk: chunk.details.chunk_number):
        number = chunk.details.chunk_number
        count = len(metadata[number].frame_meta)
        if count == 0:
            raise ValueError(f"Missing frame metadata for chunk {number}; cannot determine global frame indices.")
        offsets[number] = next_index
        counts[number] = count
        next_index += count
    return offsets, counts

def download_worker(
    ml_api_key, email, password, base_url, session_id, chunk_numbers, download_queue, tmpdir
):
    """
    Background process worker to download chunks.
    It authenticates its own API instance since active connections cannot be pickled.
    """
    from tngo_api import TngoApi

    # Initialize process-local API
    api = TngoApi(base_url=base_url, ml_api_key=ml_api_key)
    if not ml_api_key:
        api.login(email, password)
    video = api.sessions.session(session_id).video()

    for chunk_number in chunk_numbers:
        temp_vid_path = os.path.join(tmpdir, f"chunk_{chunk_number}.mp4")

        try:
            video_bytes = video[chunk_number].chunks[0].read()

            with open(temp_vid_path, 'wb') as f:
                f.write(video_bytes)

            # Add to queue. Blocks if queue is at maxsize.
            download_queue.put((chunk_number, temp_vid_path))

        except Exception as e:
            print(f"Error downloading chunk {chunk_number}: {e}")

    # Signal the main process that downloading is fully complete
    download_queue.put(None)
    api.close()

def main():
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Download a labeling session and extract all frames."
    )
    parser.add_argument("session_id", help="The user-facing Labeling Session ID")
    parser.add_argument(
        "-d",
        "--data-dir",
        default="./data",
        help="Directory to store downloaded sessions (default: ./data)",
    )
    parser.add_argument("--potholes-only", action="store_true", help="Download only chunks with potholes and their immediate neighbors")
    parser.add_argument("--format", default="jpg", help="Image format for extracted frames (default: jpg)")
    parser.add_argument(
        "--base-url",
        default=os.environ.get("TNGO_BASE_URL", "https://api.tngomtsu.com"),
        help="TNGO API base URL (default: TNGO_BASE_URL or production)",
    )

    args = parser.parse_args()

    # 1. Setup Auth
    ml_api_key = os.environ.get("ML_API_KEY")
    email = os.environ.get("TNGO_EMAIL")
    password = os.environ.get("TNGO_PASSWORD")

    if not ml_api_key and not (email and password):
        raise ValueError("Set ML_API_KEY, or both TNGO_EMAIL and TNGO_PASSWORD.")

    # Initialize API and Login
    from tngo_api import TngoApi

    api = TngoApi(base_url=args.base_url, ml_api_key=ml_api_key)
    if not ml_api_key:
        tqdm.write("Logging in to TNGO...")
        api.login(email, password)

    # 2. Look up the session details to bypass backend bug
    session_details = get_session_details(api, args.session_id)
    if not session_details:
        raise ValueError(f"Could not find a session matching session_id '{args.session_id}'.")

    # 3. Fetch all chunks using the internal session ID.
    tqdm.write("Fetching chunk metadata from API...")
    all_chunks = list(session_details.chunks(page_size=100))

    # 4. Sort and Filter chunks
    all_chunks.sort(key=lambda chunk: chunk.details.chunk_number)

    if args.potholes_only:
        pothole_numbers = {
            chunk.details.chunk_number
            for chunk in all_chunks
            if chunk.details.has_pothole_flag
        }
        keep_numbers = set()
        for n in pothole_numbers:
            keep_numbers.update([n-1, n, n+1])

        filtered_chunks = [
            chunk for chunk in all_chunks
            if chunk.details.chunk_number in keep_numbers
        ]
        tqdm.write(f"Filtering applied: Keeping {len(filtered_chunks)} out of {len(all_chunks)} chunks.")
    else:
        filtered_chunks = all_chunks

    if not filtered_chunks:
        tqdm.write("No chunks found to process. Exiting.")
        return

    # 5. Process Chunks and Extract Frames Concurrently
    os.makedirs(args.data_dir, exist_ok=True)

    session_output_path = os.path.join(args.data_dir, args.session_id)
    os.makedirs(session_output_path, exist_ok=True)

    tqdm.write("Reading full-session frame metadata for global frame indices...")
    offsets, frame_counts = frame_offsets(all_chunks, session_details.metadata())
    extracted_count = 0

    with tempfile.TemporaryDirectory() as tmpdir:
        # multiprocessing.Queue for cross-process communication
        download_queue = multiprocessing.Queue(maxsize=3)

        # Start the background downloader process
        downloader_process = multiprocessing.Process(
            target=download_worker,
            args=(
                ml_api_key, email, password, args.base_url,
                session_details.id,
                [chunk.details.chunk_number for chunk in filtered_chunks],
                download_queue, tmpdir
            ),
            daemon=True
        )
        downloader_process.start()

        # Setup the overall progress bar
        chunk_pbar = tqdm(total=len(filtered_chunks), desc="Overall Progress", position=0)

        # Main Thread: Consumer Loop
        while True:
            # Wait for the next downloaded video to be available
            item = download_queue.get()

            # None acts as our sentinel value
            if item is None:
                break

            chunk_number, temp_vid_path = item
            chunk_pbar.set_description(f"Unpacking Chunk {chunk_number}")

            # Open video
            cap = cv2.VideoCapture(temp_vid_path)

            if not cap.isOpened():
                tqdm.write(f"Warning: Failed to open video for chunk {chunk_number}")
                chunk_pbar.update(1)
                continue

            # Inner Progress Bar
            local_frame_idx = 0
            with tqdm(desc="Extracting Frames", position=1, leave=False, unit="frame") as frame_pbar:
                while True:
                    ret, frame = cap.read()
                    if not ret:
                        break  # End of video

                    if local_frame_idx >= frame_counts[chunk_number]:
                        raise ValueError(f"Chunk {chunk_number} has more video frames than its metadata.")
                    global_frame_idx = offsets[chunk_number] + local_frame_idx
                    frame_filename = f"frame_{global_frame_idx:06d}.{args.format}"
                    frame_filepath = os.path.join(session_output_path, frame_filename)

                    if not cv2.imwrite(frame_filepath, frame):
                        raise OSError(f"Could not write {frame_filepath}")
                    local_frame_idx += 1
                    extracted_count += 1
                    frame_pbar.update(1)

            cap.release()
            if local_frame_idx != frame_counts[chunk_number]:
                tqdm.write(f"Warning: Chunk {chunk_number} decoded {local_frame_idx} of {frame_counts[chunk_number]} expected frames; remaining indices are left unused.")

            # Clean up the video file
            try:
                os.remove(temp_vid_path)
            except OSError as e:
                tqdm.write(f"Warning: Could not delete {temp_vid_path}: {e}")

            chunk_pbar.update(1)

        downloader_process.join()
        chunk_pbar.close()

    tqdm.write(f"\nDone! Extracted {extracted_count} total frames to {session_output_path}")
    api.close()

if __name__ == "__main__":
    main()
