import os
import cv2
import numpy as np
import re
import time

# -------------------------------
# 🔹 UTILITY: NORMALIZE FILENAME
# -------------------------------
def normalize_filename(filename):
    """
    Normalizes a filename by:
      - Removing its extension
      - Converting all letters to lowercase
      - Replacing spaces and hyphens with underscores
    """
    name, _ = os.path.splitext(filename)
    return re.sub(r'[\s\-]+', '_', name.lower())


# -----------------------------
# 🔹 IMAGE PREPROCESSING
# -----------------------------
def resize_image(image, max_width=4000):
    """
    Resizes image while maintaining aspect ratio (max width = 4000px).
    """
    h, w = image.shape[:2]
    if w > max_width:
        ratio = max_width / w
        new_size = (int(w * ratio), int(h * ratio))
        image = cv2.resize(image, new_size, interpolation=cv2.INTER_AREA)
    return image


def preprocess_image(image_path, offset):
    """
    1) Reads the image
    2) Resizes if necessary (max width = 4000)
    3) Converts to grayscale
    4) Calculates (mean - offset) for threshold
    5) Binarizes the image
    6) Returns (final_image, final_size_bytes, local_time).
    """
    start_local = time.perf_counter()

    # 1) Read the image
    image = cv2.imread(image_path)
    if image is None:
        raise ValueError(f"Could not read image: {image_path}")

    # 2) Resize if needed
    resized = resize_image(image)

    # 3) Convert to grayscale
    gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)

    # 4) Compute threshold = mean(gray) - offset, clamped to [0..255]
    mean_val = int(gray.mean())
    threshold_val = max(0, min(255, mean_val - offset))

    # 5) Binarize
    _, bin_image = cv2.threshold(gray, threshold_val, 255, cv2.THRESH_BINARY)

    # Encode to memory buffer for size measurement
    success, buffer = cv2.imencode(".jpg", bin_image, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
    final_size_bytes = len(buffer) if success else 0

    end_local = time.perf_counter()
    local_time = end_local - start_local

    # Return the binarized image, final size, time
    return bin_image, final_size_bytes, local_time


# --------------------------------
# 🔹 MAIN: PROCESS & LOG STATS
# --------------------------------
def main():
    images_folder = "images"
    preprocessed_folder = "preprocessed_images"
    results_folder = "results"
    
    # Create necessary folders
    os.makedirs(preprocessed_folder, exist_ok=True)
    os.makedirs(results_folder, exist_ok=True)

    results_file = os.path.join(results_folder, "processing_results.txt")

    # Gather images
    all_images = [
        f for f in os.listdir(images_folder)
        if f.lower().endswith(("png", "jpg", "jpeg"))
    ]
    if not all_images:
        raise FileNotFoundError("No images found in the 'images' folder.")

    all_images.sort()

    # Combined stats
    total_preprocess_time = 0.0
    combined_original_size = 0
    combined_final_size = 0
    total_images_processed = 0

    overall_start = time.perf_counter()

    # Open the results file
    with open(results_file, "w") as results:
        results.write("=== IMAGE PREPROCESSING RESULTS ===\n\n")

        for image_file in all_images:
            image_path = os.path.join(images_folder, image_file)
            original_size = os.path.getsize(image_path)

            # Decide offset based on filename
            # - license => mean - 20
            # - passport => mean - 30
            # - otherwise => offset = 0 (just use mean)
            filename_lower = image_file.lower()
            if filename_lower.startswith("license"):
                offset = 20
            elif filename_lower.startswith("passport"):
                offset = 30
            else:
                offset = 0

            # Preprocess (resize, binarize)
            processed_image, final_size_bytes, local_time = preprocess_image(
                image_path, offset=offset
            )

            total_preprocess_time += local_time

            # Save final result
            normalized_name = normalize_filename(image_file)
            out_filename = f"{normalized_name}_preprocessed.jpg"
            save_path = os.path.join(preprocessed_folder, out_filename)
            cv2.imwrite(save_path, processed_image, [int(cv2.IMWRITE_JPEG_QUALITY), 90])

            # Update stats
            combined_original_size += original_size
            combined_final_size += final_size_bytes
            total_images_processed += 1

            # Write individual image results to the file
            results.write(f"Preprocessed: {image_file}\n")
            results.write(f"  - Original size: {original_size} bytes\n")
            results.write(f"  - Final size: {final_size_bytes} bytes\n")
            results.write(f"  - Processing time: {local_time * 1000:.2f} ms\n")
            results.write("\n")

        overall_end = time.perf_counter()
        total_runtime = overall_end - overall_start

        # Calculate size reduction
        size_reduced = combined_original_size - combined_final_size
        if combined_original_size > 0:
            size_reduced_pct = 100.0 * (1 - (combined_final_size / combined_original_size))
        else:
            size_reduced_pct = 0.0

        # Write final statistics to the results file
        results.write("\n=== SUMMARY ===\n")
        results.write(f"Total images processed:          {total_images_processed}\n")
        results.write(f"Total local preprocessing time:  {total_preprocess_time:.4f} sec\n")
        results.write(f"Combined original size:          {combined_original_size} bytes\n")
        results.write(f"Combined final size:             {combined_final_size} bytes\n")
        results.write(f"Size reduced (absolute):         {size_reduced} bytes\n")
        results.write(f"Size reduced (percentage):       {size_reduced_pct:.2f}%\n")
        results.write(f"Total runtime (all steps):       {total_runtime * 1000:.2f} ms\n")

    # Print summary in console as well
    print("\n=== PROCESS COMPLETE ===")
    print(f"Total images processed:          {total_images_processed}")
    print(f"\nTotal local preprocessing time:  {total_preprocess_time:.4f} sec")
    print(f"Combined original size:          {combined_original_size} bytes")
    print(f"Combined final size:             {combined_final_size} bytes")
    print(f"Size reduced (absolute):         {size_reduced} bytes")
    print(f"Size reduced (percentage):       {size_reduced_pct:.2f}%")
    print(f"Total runtime (all steps):       {total_runtime * 1000:.2f} ms")

    print(f"\nResults saved to: {results_file}")


if __name__ == "__main__":
    main()
