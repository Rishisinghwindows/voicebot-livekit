import Foundation

struct TokenResponse: Decodable {
    let token: String
    let url: String
}

struct UserInfo {
    var name: String = ""
    var subject: String = ""
    var grade: String = ""
    var language: String = "English"
    var type: String = ""
}

enum TokenService {
    static let baseURL = "https://advancedvoiceagent.xappy.io"

    static func fetchToken(userInfo: UserInfo) async throws -> TokenResponse {
        var components = URLComponents(string: "\(baseURL)/token")!
        components.queryItems = [
            URLQueryItem(name: "name", value: userInfo.name),
            URLQueryItem(name: "subject", value: userInfo.subject),
            URLQueryItem(name: "grade", value: userInfo.grade),
            URLQueryItem(name: "language", value: userInfo.language),
            URLQueryItem(name: "type", value: userInfo.type),
        ]
        guard let url = components.url else {
            throw URLError(.badURL)
        }
        let (data, _) = try await URLSession.shared.data(from: url)
        return try JSONDecoder().decode(TokenResponse.self, from: data)
    }
}
