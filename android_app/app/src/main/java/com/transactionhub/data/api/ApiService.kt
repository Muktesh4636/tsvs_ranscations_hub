package com.transactionhub.data.api

import com.transactionhub.data.models.*
import retrofit2.Response
import retrofit2.http.*

interface ApiService {
    @POST("api/login/")
    suspend fun login(@Body request: LoginRequest): Response<LoginResponse>
    
    @GET("api/mobile-dashboard/")
    suspend fun getDashboard(@Header("Authorization") token: String): Response<DashboardResponse>
    
    @GET("api/clients/")
    suspend fun getClients(@Header("Authorization") token: String): Response<List<Client>>
    
    @POST("api/clients/")
    suspend fun createClient(
        @Header("Authorization") token: String,
        @Body client: Client
    ): Response<Client>

    @PUT("api/clients/{id}/")
    suspend fun updateClient(
        @Header("Authorization") token: String,
        @Path("id") id: Int,
        @Body client: Client
    ): Response<Client>
    
    @GET("api/accounts/")
    suspend fun getAccounts(@Header("Authorization") token: String): Response<List<Account>>
    
    @GET("api/transactions/")
    suspend fun getTransactions(@Header("Authorization") token: String): Response<List<Transaction>>
    
    @GET("api/exchanges/")
    suspend fun getExchanges(@Header("Authorization") token: String): Response<List<Exchange>>

    @GET("api/pending-payments/")
    suspend fun getPendingPayments(@Header("Authorization") token: String): Response<PendingPaymentsResponse>

    @POST("api/accounts/{id}/funding/")
    suspend fun addFunding(
        @Header("Authorization") token: String,
        @Path("id") id: Int,
        @Body data: Map<String, String>
    ): Response<Map<String, Any>>

    @POST("api/accounts/{id}/balance/")
    suspend fun updateBalance(
        @Header("Authorization") token: String,
        @Path("id") id: Int,
        @Body data: Map<String, String>
    ): Response<Map<String, Any>>

    @POST("api/accounts/{id}/payment/")
    suspend fun recordPayment(
        @Header("Authorization") token: String,
        @Path("id") id: Int,
        @Body request: RecordPaymentRequest
    ): Response<Map<String, Any>>

    @GET("api/reports-summary/")
    suspend fun getReportsSummary(
        @Header("Authorization") token: String,
        @Query("period") period: String? = null
    ): Response<Map<String, Any>>

    @POST("api/exchanges/create/")
    suspend fun createExchange(
        @Header("Authorization") token: String,
        @Body data: Map<String, String>
    ): Response<Map<String, Any>>

    @POST("api/accounts/link/")
    suspend fun linkAccount(
        @Header("Authorization") token: String,
        @Body data: Map<String, String>
    ): Response<Map<String, Any>>

    @DELETE("api/transactions/{id}/delete/")
    suspend fun deleteTransaction(
        @Header("Authorization") token: String,
        @Path("id") id: Int
    ): Response<Map<String, Any>>

    @POST("api/transactions/{id}/edit/")
    suspend fun editTransaction(
        @Header("Authorization") token: String,
        @Path("id") id: Int,
        @Body data: Map<String, String>
    ): Response<Map<String, Any>>

    @DELETE("api/clients/{id}/delete/")
    suspend fun deleteClient(
        @Header("Authorization") token: String,
        @Path("id") id: Int
    ): Response<Map<String, Any>>

    @DELETE("api/exchanges/{id}/delete/")
    suspend fun deleteExchange(
        @Header("Authorization") token: String,
        @Path("id") id: Int
    ): Response<Map<String, Any>>

    @POST("api/accounts/{id}/settings/")
    suspend fun updateAccountSettings(
        @Header("Authorization") token: String,
        @Path("id") id: Int,
        @Body data: Map<String, String>
    ): Response<Map<String, Any>>

    @GET("api/accounts/{id}/report-config/")
    suspend fun getReportConfig(
        @Header("Authorization") token: String,
        @Path("id") id: Int
    ): Response<Map<String, Any>>

    @POST("api/accounts/{id}/report-config/")
    suspend fun updateReportConfig(
        @Header("Authorization") token: String,
        @Path("id") id: Int,
        @Body data: Map<String, String>
    ): Response<Map<String, Any>>

    @GET("api/pending/export/")
    suspend fun exportPendingPayments(
        @Header("Authorization") token: String
    ): Response<okhttp3.ResponseBody>

    @GET("api/reports/export/")
    suspend fun exportReportsCsv(
        @Header("Authorization") token: String,
        @Query("period") period: String? = null
    ): Response<okhttp3.ResponseBody>

    @GET("reports/custom/")
    suspend fun getCustomReports(
        @Header("Authorization") token: String,
        @Query("from_date") fromDate: String,
        @Query("to_date") toDate: String,
        @Query("client_id") clientId: String? = null,
        @Query("exchange_id") exchangeId: String? = null
    ): Response<Map<String, Any>>
}
