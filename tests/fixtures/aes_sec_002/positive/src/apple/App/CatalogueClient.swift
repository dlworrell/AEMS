import Foundation

private final class CDatabaseOwner {
    private var isOpen = false

    func adopt() {
        isOpen = true
    }

    func close() {
        if isOpen {
            ab_database_close()
            isOpen = false
        }
    }

    deinit {
        close()
    }
}

@MainActor
final class CatalogueClient {
    private let owner = CDatabaseOwner()

    func open(key: Data) throws {
        var mutableKey = key
        defer {
            mutableKey.resetBytes(in: mutableKey.indices)
        }
        _ = mutableKey.withUnsafeBytes { bytes in
            ab_database_open_encrypted(
                bytes.bindMemory(to: UInt8.self).baseAddress,
                bytes.count
            )
        }
        owner.adopt()
    }
}
