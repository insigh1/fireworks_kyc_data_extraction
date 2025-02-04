import os
import json
import base64
import requests
from dotenv import load_dotenv
import re
import time  # for timing

# Load environment variables
load_dotenv()

# Fireworks API credentials
FIREWORKS_API_KEY = os.getenv("FIREWORKS_API_KEY")
FIREWORKS_ENDPOINT = os.getenv("FIREWORKS_ENDPOINT")
FIREWORKS_MODEL = os.getenv("FIREWORKS_MODEL")

print(f"Loaded Endpoint: {FIREWORKS_ENDPOINT}")
print(f"Loaded Model: {FIREWORKS_MODEL}")

# Ensure API Key and Endpoint are available
if not FIREWORKS_API_KEY or not FIREWORKS_ENDPOINT:
    raise ValueError("Missing Fireworks API credentials in environment variables.")

images_folder = "preprocessed_images"
results_folder = "results"
os.makedirs(results_folder, exist_ok=True)  # Ensure results folder exists
results_file = os.path.join(results_folder, "text_extracted_results.txt")

image_files = [f for f in os.listdir(images_folder) if f.lower().endswith(("png", "jpg", "jpeg"))]

if not image_files:
    raise FileNotFoundError("No images found in the 'preprocessed_images' folder.")

# 1. Read all images and build a single "user" content array
batch_content = []
instructions_text = (
    "We have multiple ID images. For each image, extract all text in an organized way. "
    "I don't need a physical description of the person. I only want these printed text fields:\n\n"
    "First name, Last name, Date of birth (DOB), Address, State, Country, "
    "Drivers license (DL) number or passport number, Sex, Height (HGT), Weight (WGT), "
    "Hair, Eyes, Issue date (ISS), Expiration date (EXP).\n\n"
    "For any missing fields, respond with 'N/A'. Please return the final result in JSON, "
    "as an array of objects. Each object should correspond to a single image and have the structure:\n\n"
    "  {\n"
    "    \"filename\": <string>,\n"
    "    \"id_type\": <string>,\n"
    "    \"id_number\": <string>,\n"
    "    \"first_name\": <string>,\n"
    "    \"last_name\": <string>,\n"
    "    \"dob\": <string>,\n"
    "    \"place of birth\": <string>,\n"
    "    \"address\": <string>,\n"
    "    \"state\": <string>,\n"
    "    \"country\": <string>,\n"
    "    \"class\": <string>,\n"
    "    \"sex\": <string>,\n"
    "    \"hgt\": <string>,\n"
    "    \"wgt\": <string>,\n"
    "    \"hair\": <string>,\n"
    "    \"eyes\": <string>,\n"
    "    \"issue_date_iss\": <string>,\n"
    "    \"expiration_date_exp\": <string>\n"
    "  }\n"
    "Use snake_case for the JSON keys, as shown above."
)

# Add one text block containing the overall instructions
batch_content.append({
    "type": "text",
    "text": instructions_text
})

# For each image, insert it into the prompt
for image_file in image_files:
    # Detect id_type from the filename
    if image_file.lower().startswith("license"):
        id_type = "drivers_license"
    elif image_file.lower().startswith("passport"):
        id_type = "passport"
    else:
        id_type = "N/A"

    image_path = os.path.join(images_folder, image_file)
    with open(image_path, "rb") as img_f:
        encoded = base64.b64encode(img_f.read()).decode("utf-8")
    
    # Add an image block
    batch_content.append({
        "type": "image_url",
        "image_url": {
            "url": f"data:image/jpeg;base64,{encoded}"
        }
    })
    # Add a short text prompt referencing the specific file and ID type
    batch_content.append({
        "type": "text",
        "text": (
            f"This image is named {image_file}. The ID type for this image is {id_type}. "
            f"Extract the text and include the correct 'id_type' in the JSON output."
        )
    })

# 2. Create a single messages list for the conversation
messages = [
    {
        "role": "user",
        "content": batch_content
    }
]

# 3. Prepare the overall payload
payload = {
    "model": FIREWORKS_MODEL,
    "max_tokens": 4096,
    "top_p": 1,
    "top_k": 100,
    "presence_penalty": 0,
    "frequency_penalty": 0,
    "temperature": 0,
    "messages": messages
}

headers = {
    "Accept": "application/json",
    "Content-Type": "application/json",
    "Authorization": f"Bearer {FIREWORKS_API_KEY}"
}

# Record start time (for performance measurement)
start_time = time.time()

# (1) We have exactly ONE API call here
total_api_calls = 1

# Send the request
response = requests.post(FIREWORKS_ENDPOINT, headers=headers, data=json.dumps(payload))

# Record end time
end_time = time.time()

# Calculate duration in milliseconds
duration_ms = (end_time - start_time) * 1000
average_ms_per_image = duration_ms / len(image_files)

# Open results file to store extracted text
with open(results_file, "w") as results:

    # Check response
    if response.status_code == 200:
        try:
            response_json = response.json()
            if "choices" not in response_json or not response_json["choices"]:
                print("No valid content found in the response.")
            else:
                # The entire response from the Assistant
                content = response_json["choices"][0]["message"]["content"]
                
                # --- Remove triple backticks if present ---
                content_str = content.strip()
                if content_str.startswith("```") and content_str.endswith("```"):
                    lines = content_str.splitlines()
                    # Remove the first and last line: ```json and ```
                    lines = lines[1:-1]
                    content_str = "\n".join(lines).strip()

                # Attempt to parse JSON
                try:
                    extracted_batch = json.loads(content_str)

                    # If id_type == 'passport', keep only the first 9 numeric digits in id_number

                    for item in extracted_batch:
                        if item.get("id_type") == "passport":
                            original_id = item.get("id_number", "")
                            # Extract only digits
                            digits_only = "".join(ch for ch in original_id if ch.isdigit())
                            # Keep only first 9
                            item["id_number"] = digits_only[:9]

                        results.write(json.dumps(item, indent=4) + "\n\n")

                    print("\nExtracted text saved to:", results_file)

                    print("\nParsed JSON:\n", json.dumps(extracted_batch, indent=4))
                except json.JSONDecodeError:
                    results.write("The assistant response was not valid JSON.\n")
                    print("The assistant response was not valid JSON even after removing code fences.")

            # Attempt to extract token usage if provided
            usage_info = response_json.get("usage", {})
            prompt_tokens = usage_info.get("prompt_tokens", 0)
            completion_tokens = usage_info.get("completion_tokens", 0)
            total_tokens = usage_info.get("total_tokens", 0)

            results.write("\n--- Performance & Design Statistics ---\n")
            results.write(f"Number of images processed: {len(image_files)}\n")
            results.write(f"Total number of API calls: {total_api_calls}\n")
            results.write(f"Total time for request: {duration_ms:.2f} ms\n")
            results.write(f"Average time per image: {average_ms_per_image:.2f} ms\n")

            # Write token statistics
            results.write("\n--- Usage / Token Statistics ---\n")
            results.write(f"  Prompt tokens: {prompt_tokens}\n")
            results.write(f"  Completion tokens: {completion_tokens}\n")
            results.write(f"  Total tokens used: {total_tokens}\n")

        except json.JSONDecodeError:
            results.write("Error: Unable to parse response as JSON.\n")
            print("Error: Unable to parse response as JSON.")

            # If usage is not parsed yet, define it here
            prompt_tokens = 0
            completion_tokens = 0
            total_tokens = 0
    else:
        print(f"Error {response.status_code}: {response.text}")
        results.write(error_msg)
        print(error_msg)
        
        # If request fails, define usage counters as 0
        prompt_tokens = 0
        completion_tokens = 0
        total_tokens = 0

# Print performance statistics
print("\n--- Performance & Design Statistics ---")
print(f"Number of images processed: {len(image_files)}")
print(f"Total number of API calls: {total_api_calls}")
print(f"Total time for request: {duration_ms:.2f} ms")
print(f"Average time per image: {average_ms_per_image:.2f} ms\n")

print("Usage / Token Statistics:")
print(f"  Prompt tokens: {prompt_tokens}")
print(f"  Completion tokens: {completion_tokens}")
print(f"  Total tokens used: {total_tokens}\n")
