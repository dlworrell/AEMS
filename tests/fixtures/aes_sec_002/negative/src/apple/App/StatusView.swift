import SwiftUI

struct StatusView: View {
    var body: some View {
        Button("Unsafe") {
            ab_database_close()
        }
    }
}
