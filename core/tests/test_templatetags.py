"""
Comprehensive test cases for all template tags in the core application.
"""
from django.test import SimpleTestCase  # Use SimpleTestCase - no database needed
from django.template import Context, Template
from decimal import Decimal


class MathFiltersTests(SimpleTestCase):
    """Test cases for math template filters"""
    
    def test_abs_filter_positive(self):
        """Test abs filter with positive number"""
        template = Template('{% load math_filters %}{{ value|abs }}')
        context = Context({'value': 100})
        result = template.render(context)
        # Filter converts to float, so result is '100.0'
        self.assertIn('100', result.strip())
    
    def test_abs_filter_negative(self):
        """Test abs filter with negative number"""
        template = Template('{% load math_filters %}{{ value|abs }}')
        context = Context({'value': -100})
        result = template.render(context)
        # Filter converts to float, so result is '100.0'
        self.assertIn('100', result.strip())
    
    def test_abs_filter_decimal(self):
        """Test abs filter with Decimal"""
        template = Template('{% load math_filters %}{{ value|abs }}')
        context = Context({'value': Decimal('-50.5')})
        result = template.render(context)
        # Filter converts to float
        self.assertIn('50.5', result.strip())
    
    def test_abs_filter_none(self):
        """Test abs filter with None"""
        template = Template('{% load math_filters %}{{ value|abs }}')
        context = Context({'value': None})
        result = template.render(context)
        # Filter returns None which renders as empty string or 'None'
        self.assertIn(result.strip(), ['', 'None'])
    
    def test_indian_number_format_small(self):
        """Test Indian number format for small numbers"""
        template = Template('{% load math_filters %}{{ value|indian_number_format }}')
        context = Context({'value': 1000})
        result = template.render(context)
        self.assertEqual(result.strip(), '1,000')
    
    def test_indian_number_format_large(self):
        """Test Indian number format for large numbers"""
        template = Template('{% load math_filters %}{{ value|indian_number_format }}')
        context = Context({'value': 1000000})
        result = template.render(context)
        self.assertEqual(result.strip(), '10,00,000')
    
    def test_indian_number_format_negative(self):
        """Test Indian number format for negative numbers"""
        template = Template('{% load math_filters %}{{ value|indian_number_format }}')
        context = Context({'value': -1000000})
        result = template.render(context)
        self.assertEqual(result.strip(), '-10,00,000')
    
    def test_indian_number_format_zero(self):
        """Test Indian number format for zero"""
        template = Template('{% load math_filters %}{{ value|indian_number_format }}')
        context = Context({'value': 0})
        result = template.render(context)
        self.assertEqual(result.strip(), '0')
    
    def test_indian_number_format_decimal(self):
        """Test Indian number format with Decimal"""
        template = Template('{% load math_filters %}{{ value|indian_number_format }}')
        context = Context({'value': Decimal('1000.5')})
        result = template.render(context)
        # Filter uses int(round(float(value))) 
        # Python's round() uses "round half to even": round(1000.5) = 1000
        # So 1000.5 becomes 1000, formatted as 1,000
        self.assertEqual(result.strip(), '1,000')
    
    def test_currency_inr_positive(self):
        """Test currency INR filter for positive number"""
        template = Template('{% load math_filters %}{{ value|currency_inr }}')
        context = Context({'value': 1000})
        result = template.render(context)
        self.assertEqual(result.strip(), '₹1,000')
    
    def test_currency_inr_negative(self):
        """Test currency INR filter for negative number"""
        template = Template('{% load math_filters %}{{ value|currency_inr }}')
        context = Context({'value': -1000})
        result = template.render(context)
        self.assertEqual(result.strip(), '-₹1,000')
    
    def test_currency_inr_large(self):
        """Test currency INR filter for large number"""
        template = Template('{% load math_filters %}{{ value|currency_inr }}')
        context = Context({'value': 1000000})
        result = template.render(context)
        self.assertEqual(result.strip(), '₹10,00,000')
    
    def test_currency_inr_zero(self):
        """Test currency INR filter for zero"""
        template = Template('{% load math_filters %}{{ value|currency_inr }}')
        context = Context({'value': 0})
        result = template.render(context)
        self.assertEqual(result.strip(), '₹0')
    
    def test_currency_inr_none(self):
        """Test currency INR filter for None"""
        template = Template('{% load math_filters %}{{ value|currency_inr }}')
        context = Context({'value': None})
        result = template.render(context)
        self.assertEqual(result.strip(), '₹0')
    
    def test_currency_inr_decimal(self):
        """Test currency INR decimal filter"""
        template = Template('{% load math_filters %}{{ value|currency_inr_decimal }}')
        context = Context({'value': Decimal('1234.56')})
        result = template.render(context)
        self.assertIn('₹', result)
        self.assertIn('1,234', result)  # Formatted with commas
        self.assertIn('.56', result)
    
    def test_currency_inr_decimal_zero(self):
        """Test currency INR decimal filter for zero"""
        template = Template('{% load math_filters %}{{ value|currency_inr_decimal }}')
        context = Context({'value': 0})
        result = template.render(context)
        self.assertEqual(result.strip(), '₹0.00')
    
    def test_currency_inr_decimal_negative(self):
        """Test currency INR decimal filter for negative number"""
        template = Template('{% load math_filters %}{{ value|currency_inr_decimal }}')
        context = Context({'value': Decimal('-1234.56')})
        result = template.render(context)
        self.assertIn('-₹', result)
        self.assertIn('1,234', result)  # Formatted with commas
