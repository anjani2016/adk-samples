# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import argparse
import os
import tempfile

import requests
from google.auth import default
import vertexai
from vertexai.preview import rag
from dotenv import load_dotenv, set_key

# Load environment variables from .env file
load_dotenv()

# --- Please fill in your configurations ---
# Retrieve the PROJECT_ID from the environmental variables.
PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT")
if not PROJECT_ID:
    raise ValueError(
        "GOOGLE_CLOUD_PROJECT environment variable not set. Please set it in your .env file."
    )
LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION")
if not LOCATION:
    raise ValueError(
        "GOOGLE_CLOUD_LOCATION environment variable not set. Please set it in your .env file."
    )
CORPUS_DISPLAY_NAME = "Alphabet_10K_2024_corpus"
CORPUS_DESCRIPTION = "Corpus containing Alphabet's 10-K 2024 document"
PDF_URL = "https://abc.xyz/assets/77/51/9841ad5c4fbe85b4440c47a4df8d/goog-10-k-2024.pdf"
PDF_FILENAME = "goog-10-k-2024.pdf"
ENV_FILE_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))


# --- Start of the script ---
def initialize_vertex_ai():
  credentials, _ = default()
  vertexai.init(
      project=PROJECT_ID, location=LOCATION, credentials=credentials
  )


def create_or_get_corpus(display_name, description):
  """Creates a new corpus or retrieves an existing one."""
  embedding_model_config = rag.EmbeddingModelConfig(
      publisher_model="publishers/google/models/text-embedding-004"
  )
  existing_corpora = rag.list_corpora()
  corpus = None
  for existing_corpus in existing_corpora:
    if existing_corpus.display_name == display_name:
      corpus = existing_corpus
      print(f"Found existing corpus with display name '{display_name}'")
      break
  if corpus is None:
    corpus = rag.create_corpus(
        display_name=display_name,
        description=description,
        embedding_model_config=embedding_model_config,
    )
    print(f"Created new corpus with display name '{display_name}'")
  return corpus


def download_pdf_from_url(url, output_path):
  """Downloads a PDF file from the specified URL."""
  print(f"Downloading PDF from {url}...")
  response = requests.get(url, stream=True)
  response.raise_for_status()  # Raise an exception for HTTP errors
  
  with open(output_path, 'wb') as f:
    for chunk in response.iter_content(chunk_size=8192):
      f.write(chunk)
  
  print(f"PDF downloaded successfully to {output_path}")
  return output_path


def upload_pdf_to_corpus(corpus_name, pdf_path, display_name, description):
  """Uploads a PDF file to the specified corpus."""
  print(f"Uploading {display_name} to corpus...")
  try:
    rag_file = rag.upload_file(
        corpus_name=corpus_name,
        path=pdf_path,
        display_name=display_name,
        description=description,
    )
    print(f"Successfully uploaded {display_name} to corpus")
    return rag_file
  except Exception as e:
    print(f"Error uploading file {display_name}: {e}")
    return None

def import_from_gcs(corpus_name, gcs_uri):
  """Imports files from a GCS URI into the specified corpus."""
  print(f"Starting import from GCS URI {gcs_uri} into corpus {corpus_name}...")
  try:
    # This is an async operation and can take a while for large folders.
    # The second return value is a list of failed imports.
    rag.import_files(
        corpus_name=corpus_name,
        paths=[gcs_uri],
        # You can specify chunking strategy here if needed
        # e.g., transformation_config=rag.TransformationConfig(...)
    )
    print(f"Successfully started import job from {gcs_uri}.")
    print("It may take some time for the files to be fully indexed.")
  except Exception as e:
    print(f"Error importing from GCS URI {gcs_uri}: {e}")
    return None

def update_env_file(corpus_name, env_file_path):
    """Updates the .env file with the corpus name."""
    try:
        set_key(env_file_path, "RAG_CORPUS", corpus_name)
        print(f"Updated RAG_CORPUS in {env_file_path} to {corpus_name}")
    except Exception as e:
        print(f"Error updating .env file: {e}")

def list_corpus_files(corpus_name):
  """Lists files in the specified corpus."""
  files = list(rag.list_files(corpus_name=corpus_name))
  print(f"Total files in corpus: {len(files)}")
  for file in files:
    print(f"File: {file.display_name} - {file.name}")


def main():
  parser = argparse.ArgumentParser(
      description="Prepare and upload data to a Vertex AI RAG Corpus."
  )
  parser.add_argument(
      "--local-file-path",
      type=str,
      help="Path to a local PDF file to upload. If not provided, will download from PDF_URL.",
  )
  parser.add_argument(
      "--display-name",
      type=str,
      help="Display name for the uploaded file. Defaults to the filename.",
  )
  parser.add_argument(
      "--description",
      type=str,
      help="Description for the uploaded file.",
  )
  parser.add_argument(
      "--gcs-uri",
      type=str,
      help="GCS URI of a folder to import (e.g., 'gs://my-bucket/my-docs/'). This will import all files recursively.",
  )
  parser.add_argument(
      "--corpus-display-name",
      type=str,
      default="Alphabet_10K_2024_corpus",
      help="Display name for the RAG Corpus.",
  )
  parser.add_argument(
      "--corpus-description",
      type=str,
      default="Corpus containing Alphabet's 10-K 2024 document",
      help="Description for the RAG Corpus.",
  )
  parser.add_argument(
      "--pdf-url",
      type=str,
      default="https://abc.xyz/assets/77/51/9841ad5c4fbe85b4440c47a4df8d/goog-10-k-2024.pdf",
      help="URL of the PDF to download if --local-file-path is not provided.",
  )
  parser.add_argument(
      "--pdf-filename",
      type=str,
      default="goog-10-k-2024.pdf",
      help="Filename to use for the downloaded PDF.",
  )
  args = parser.parse_args()

  initialize_vertex_ai()
  corpus = create_or_get_corpus(
      display_name=args.corpus_display_name, description=args.corpus_description
  )

  # Update the .env file with the corpus name
  update_env_file(corpus.name, ENV_FILE_PATH)

  if args.gcs_uri:
    import_from_gcs(corpus.name, args.gcs_uri)
  elif args.local_file_path:
    if os.path.exists(args.local_file_path):
      display_name = args.display_name or os.path.basename(args.local_file_path)
      description = args.description or f"Uploaded file: {display_name}"
      upload_pdf_to_corpus(
          corpus_name=corpus.name,
          pdf_path=args.local_file_path,
          display_name=display_name,
          description=description,
      )
    else:
      print(f"Error: Local file not found at {args.local_file_path}")
  else:
    # Default behavior: download from URL
    with tempfile.TemporaryDirectory() as temp_dir:
      pdf_path = os.path.join(temp_dir, args.pdf_filename)
      download_pdf_from_url(args.pdf_url, pdf_path)
      upload_pdf_to_corpus(
          corpus_name=corpus.name,
          pdf_path=pdf_path,
          display_name=args.pdf_filename,
          description="Alphabet's 10-K 2024 document",
      )

  # List all files in the corpus
  list_corpus_files(corpus_name=corpus.name)

if __name__ == "__main__":
  main()
