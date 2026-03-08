package com.ubudy.voiceai

import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import retrofit2.http.GET
import retrofit2.http.Query

data class TokenResponse(val token: String, val url: String)

data class UserInfo(
    val name: String = "",
    val subject: String = "",
    val grade: String = "",
    val language: String = "English"
)

interface TokenService {
    @GET("/token")
    suspend fun getToken(
        @Query("name") name: String = "",
        @Query("subject") subject: String = "",
        @Query("grade") grade: String = "",
        @Query("language") language: String = "English"
    ): TokenResponse
}

object TokenClient {
    private const val BASE_URL = "https://advancedvoiceagent.xappy.io"

    val service: TokenService by lazy {
        Retrofit.Builder()
            .baseUrl(BASE_URL)
            .addConverterFactory(GsonConverterFactory.create())
            .build()
            .create(TokenService::class.java)
    }
}
