from retriever import retrieve

# Ask the user a question
question = input("Ask a question: ")

results = retrieve(
    question,
    n_results=10
)

print("\nTop Matches\n")

for i in range(len(results["documents"][0])):

    print("=" * 70)

    metadata = results["metadatas"][0][i]

    print(f"Rank : {i + 1}")
    print(f"File : {metadata['file']}")
    print(f"Page : {metadata['page']}")
    print()

    print(results["documents"][0][i][:700])
    print()