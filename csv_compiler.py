import pandas as pd

# Load the deduplicated CSV
file_path = "/Users/teez/Development/Claude/OpenManus/combined_results_deduplicated.csv"
df = pd.read_csv(file_path)

# Define chunk size
chunk_size = 1500

# Split and save into separate files
for i, chunk in enumerate(range(0, len(df), chunk_size)):
    output_file = f"split_results_part_{i+1}.csv"
    df.iloc[chunk : chunk + chunk_size].to_csv(output_file, index=False)
    print(f"Saved: {output_file}")

print("Splitting complete!")
