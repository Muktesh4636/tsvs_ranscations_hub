package com.transactionhub.utils

import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import com.transactionhub.data.api.ApiService

object ApiClient {
    // TODO: Replace with your server URL
    // For local testing: Use your Mac's IP address (e.g., "http://192.168.1.100:8000")
    // For production: Use your deployed domain (e.g., "https://chip.pravoo.in")
    private const val BASE_URL = "https://svs.transactions.pravoo.in/"
    
    private val loggingInterceptor = HttpLoggingInterceptor().apply {
        level = HttpLoggingInterceptor.Level.BODY
    }
    
    private val okHttpClient = OkHttpClient.Builder()
        .addInterceptor(loggingInterceptor)
        .build()
    
    private val retrofit = Retrofit.Builder()
        .baseUrl(BASE_URL)
        .client(okHttpClient)
        .addConverterFactory(GsonConverterFactory.create())
        .build()
    
    val apiService: ApiService = retrofit.create(ApiService::class.java)
    
    fun getAuthToken(token: String): String {
        return "Token $token"
    }
}
