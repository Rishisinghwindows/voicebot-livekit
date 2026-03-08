package com.ubudy.voiceai

import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import retrofit2.http.GET

data class TokenResponse(val token: String, val url: String)

interface TokenService {
    @GET("/token")
    suspend fun getToken(): TokenResponse
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
