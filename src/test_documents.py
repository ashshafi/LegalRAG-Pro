def main() -> None:
    from document_manager import get_documents

    docs = get_documents()

    print(docs)


if __name__ == "__main__":
    main()
