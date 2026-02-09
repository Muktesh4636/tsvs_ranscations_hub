package com.transactionhub.ui.exchanges

import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.EditText
import android.widget.Toast
import androidx.fragment.app.Fragment
import androidx.lifecycle.lifecycleScope
import com.transactionhub.R
import com.transactionhub.data.api.ApiService
import com.transactionhub.utils.ApiClient
import com.transactionhub.utils.PrefManager
import kotlinx.coroutines.launch

class ExchangeCreateFragment : Fragment() {
    private lateinit var prefManager: PrefManager
    private lateinit var apiService: ApiService
    
    override fun onCreateView(inflater: LayoutInflater, container: ViewGroup?, savedInstanceState: Bundle?): View? {
        return inflater.inflate(R.layout.fragment_exchange_create, container, false)
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)
        prefManager = PrefManager(requireContext())
        apiService = ApiClient.apiService
        
        view.findViewById<Button>(R.id.btnCreateExchange).setOnClickListener {
            val name = view.findViewById<EditText>(R.id.editExchangeName).text.toString()
            val version = view.findViewById<EditText>(R.id.editExchangeVersion).text.toString()
            val code = view.findViewById<EditText>(R.id.editExchangeCode).text.toString()
            
            if (name.isEmpty()) {
                Toast.makeText(context, "Name is required", Toast.LENGTH_SHORT).show()
                return@setOnClickListener
            }
            
            createExchange(name, version, code)
        }
    }

    private fun createExchange(name: String, version: String, code: String) {
        val token = prefManager.getToken() ?: return
        val data = mapOf("name" to name, "version" to version, "code" to code)
        
        lifecycleScope.launch {
            try {
                val response = apiService.createExchange(ApiClient.getAuthToken(token), data)
                if (response.isSuccessful) {
                    Toast.makeText(context, "Exchange Added!", Toast.LENGTH_SHORT).show()
                    parentFragmentManager.popBackStack()
                } else {
                    // Try to extract error message from response
                    val errorBody = response.errorBody()?.string()
                    val errorMessage = if (errorBody != null) {
                        try {
                            // Try to parse JSON error response
                            val json = org.json.JSONObject(errorBody)
                            json.optString("error", "Error adding exchange")
                        } catch (e: Exception) {
                            "Error adding exchange"
                        }
                    } else {
                        "Error adding exchange"
                    }
                    Toast.makeText(context, errorMessage, Toast.LENGTH_LONG).show()
                    android.util.Log.e("ExchangeCreate", "Error: ${response.code()} - $errorBody")
                }
            } catch (e: Exception) {
                Toast.makeText(context, "Network error: ${e.message}", Toast.LENGTH_LONG).show()
                android.util.Log.e("ExchangeCreate", "Exception", e)
            }
        }
    }
}
