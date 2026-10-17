
func unsafeLifecycle() {
    let pointer = UnsafeMutablePointer<UInt8>.allocate(capacity: 8)
    pointer.initialize(repeating: 0, count: 8)
    pointer.deinitialize(count: 8)
    pointer.deallocate()
}

struct OrdinaryAllocator {
    func allocate(capacity: Int) -> Int { capacity }
}
func safeValueOperations() {
    _ = OrdinaryAllocator().allocate(capacity: 8)
    _ = Array(repeating: UInt8(0), count: 8)
}
