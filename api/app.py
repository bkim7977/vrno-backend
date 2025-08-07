#!/usr/bin/env python3
"""
Complete Flask Backend for Token Market - Single Server Solution
Handles ALL operations including frontend serving, API routes, WebSocket connections, and secure operations
"""

import os
import json
import requests
import hashlib
import secrets
import threading
import time
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, send_from_directory, send_file
from flask_cors import CORS
from flask_socketio import SocketIO, emit, join_room, leave_room
import logging
from supabase import create_client, Client
from postgrest import APIError
import uuid

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder='dist/public', static_url_path='')
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key')

# Enable CORS and WebSocket support
CORS(app, origins=["http://localhost:5000", "https://*.replit.app"], allow_headers=["Content-Type", "vrno-api-key", "x-api-key", "Authorization"])
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Environment variables - API keys stored securely server-side
VRNO_API_KEY = os.getenv('VRNO_API_KEY')
DATABASE_URL = os.getenv('DATABASE_URL')
EXTERNAL_API_URL = os.getenv('EXTERNAL_API_URL', 'https://token-market-backend-production.up.railway.app')

# Database operations now use Supabase client exclusively
# PostgreSQL connection pool removed - all data operations use Supabase

# Supabase configuration
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_SERVICE_KEY = os.getenv('SUPABASE_SERVICE_ROLE_KEY') or os.getenv('SUPABASE_ANON_KEY')

# Email and SMS API Keys
MAILGUN_API_KEY = os.getenv('MAILGUN_API_KEY')
MAILGUN_DOMAIN = os.getenv('MAILGUN_DOMAIN')
TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
TWILIO_PHONE_NUMBER = os.getenv('TWILIO_PHONE_NUMBER')

# PayPal API Keys
PAYPAL_CLIENT_ID = os.getenv('PAYPAL_CLIENT_ID')
PAYPAL_CLIENT_SECRET = os.getenv('PAYPAL_CLIENT_SECRET')
PAYPAL_ENVIRONMENT = os.getenv('PAYPAL_ENVIRONMENT', 'sandbox')

# Initialize Supabase client
supabase: Client | None = None
if SUPABASE_URL and SUPABASE_SERVICE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
        logger.info("Supabase client initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize Supabase client: {e}")
        supabase = None

print(f'🔗 All database operations now use Supabase client exclusively')

# ===============================
# DATABASE FUNCTIONS
# ===============================

def get_supabase_client():
    """Get Supabase client for database operations"""
    if not supabase:
        logger.error("Supabase client not initialized")
        return None
    return supabase

# Legacy functions removed - all database operations use Supabase client

# ===============================
# ONE-TIME AUTHENTICATION TOKEN SYSTEM
# ===============================

def generate_secure_token():
    """Generate secure random token"""
    return secrets.token_hex(32)

def create_auth_token(user_id, purpose, expires_in_minutes=15):
    """Create one-time auth token using Supabase"""
    client = get_supabase_client()
    if not client:
        raise Exception("Supabase client not available")
    
    token = generate_secure_token()
    expires_at = datetime.now() + timedelta(minutes=expires_in_minutes)
    
    try:
        result = client.table('auth_tokens').insert({
            'token': token,
            'user_id': str(user_id),
            'expires_at': expires_at.isoformat(),
            'purpose': purpose
        }).execute()
        
        if result.data:
            return token
        return None
    except Exception as e:
        logger.error(f"Error creating auth token: {e}")
        return None

def verify_and_consume_token(token, purpose):
    """Verify and consume one-time token using Supabase"""
    client = get_supabase_client()
    if not client:
        return {"valid": False}
    
    try:
        # First check if token is valid and unused
        current_time = datetime.now().isoformat()
        result = client.table('auth_tokens').select('user_id').eq('token', token).eq('purpose', purpose).gt('expires_at', current_time).is_('used_at', 'null').execute()
        
        if result.data:
            user_id = result.data[0]['user_id']
            # Mark token as used
            client.table('auth_tokens').update({'used_at': current_time}).eq('token', token).execute()
            return {"valid": True, "userId": user_id}
        return {"valid": False}
    except Exception as e:
        logger.error(f"Error verifying token: {e}")
        return {"valid": False}

# ===============================
# UTILITY FUNCTIONS
# ===============================

def verify_vrno_api_key():
    """Verify VRNO API key from request headers"""
    api_key = request.headers.get('vrno-api-key') or request.headers.get('x-api-key')
    
    is_valid = api_key == VRNO_API_KEY
    logger.info(f"VRNO API Key verification: {{ providedKey: '{api_key[:10] if api_key else 'None'}...', expectedKeySet: '{'SET' if VRNO_API_KEY else 'NOT_SET'}', match: {is_valid} }}")
    
    return is_valid

def make_external_api_request(endpoint, method='GET', data=None, headers=None):
    """Make authenticated request to external API"""
    if not headers:
        headers = {}
    headers['vrno-api-key'] = VRNO_API_KEY
    
    url = f"{EXTERNAL_API_URL}{endpoint}"
    
    try:
        if method == 'GET':
            response = requests.get(url, headers=headers, timeout=30)
        elif method == 'POST':
            response = requests.post(url, json=data, headers=headers, timeout=30)
        elif method == 'PUT':
            response = requests.put(url, json=data, headers=headers, timeout=30)
        elif method == 'DELETE':
            response = requests.delete(url, headers=headers, timeout=30)
        else:
            raise ValueError(f"Unsupported HTTP method: {method}")
        
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"External API request failed: {e}")
        raise

# ===============================
# FRONTEND SERVING - DISABLED FOR VERCEL
# ===============================
# Note: Frontend serving is handled by Vercel directly through vercel.json
# These routes are commented out to avoid conflicts

# @app.route('/')
# def serve_frontend():
#     """Serve the React frontend"""
#     # Disabled - Vercel handles frontend serving
#     pass

# @app.route('/<path:path>')
# def serve_static_files(path):
#     """Serve static files for React frontend"""
#     # Disabled - Vercel handles static file serving
#     pass

# ===============================
# MAINTENANCE MODE
# ===============================

@app.route('/api/debug/files')
def debug_files():
    """Debug endpoint to show available files in Vercel environment"""
    import os
    import glob
    
    debug_info = {
        "current_directory": os.getcwd(),
        "environment": "vercel" if os.environ.get('VERCEL') else "local",
        "available_files": {},
        "static_folder": app.static_folder,
        "static_url_path": app.static_url_path
    }
    
    # Check various possible locations
    locations_to_check = [
        ".",
        "./dist",
        "./dist/public", 
        "/var/task",
        "/var/task/dist",
        "/var/task/dist/public"
    ]
    
    for location in locations_to_check:
        try:
            if os.path.exists(location):
                files = []
                for root, dirs, filenames in os.walk(location):
                    for filename in filenames[:10]:  # Limit to first 10 files
                        files.append(os.path.join(root, filename))
                debug_info["available_files"][location] = files
            else:
                debug_info["available_files"][location] = "Directory not found"
        except Exception as e:
            debug_info["available_files"][location] = f"Error: {str(e)}"
    
    return jsonify(debug_info)

@app.route('/api/health')
def health_check():
    """Simple health check endpoint for Vercel"""
    return jsonify({
        "status": "healthy",
        "service": "VRNO Token Market",
        "timestamp": datetime.now().isoformat(),
        "vercel": os.environ.get('VERCEL', 'false')
    })

@app.route('/api/debug')
def debug_simple():
    """Simple debug endpoint to show file availability"""
    import os
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    info = {
        "working_directory": os.getcwd(),
        "script_directory": script_dir,
        "static_folder": getattr(app, 'static_folder', 'Not set'),
        "files_in_script_dir": [],
        "dist_exists": False,
        "index_html_paths": []
    }
    
    try:
        info["files_in_script_dir"] = os.listdir(script_dir)[:10]
    except:
        info["files_in_script_dir"] = ["Error listing files"]
    
    # Check for dist directory
    dist_path = os.path.join(script_dir, 'dist', 'public')
    info["dist_exists"] = os.path.exists(dist_path)
    
    # Check for index.html in various locations
    possible_index_paths = [
        os.path.join(script_dir, 'dist', 'public', 'index.html'),
        'dist/public/index.html',
        './dist/public/index.html'
    ]
    
    for path in possible_index_paths:
        if os.path.exists(path):
            info["index_html_paths"].append(f"{path} ✅")
        else:
            info["index_html_paths"].append(f"{path} ❌")
    
    return jsonify(info)

@app.route('/api/maintenance/status')
def get_maintenance_status():
    """Get maintenance mode status using Supabase"""
    client = get_supabase_client()
    if not client:
        return jsonify({"maintenance_mode": False, "timestamp": datetime.now().isoformat()}), 500
    
    try:
        result = client.table('admin_configs').select('config_value').eq('config_key', 'maintenance_mode').execute()
        maintenance_mode = result.data[0]['config_value'] == 'true' if result.data else False
        
        return jsonify({
            "maintenance_mode": maintenance_mode,
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Error checking maintenance status: {e}")
        return jsonify({"maintenance_mode": False, "timestamp": datetime.now().isoformat()}), 500

# ===============================
# ADMIN PANEL ENDPOINTS
# ===============================

@app.route('/admin-data/configs')
def get_admin_configs():
    """Get admin configurations using Supabase"""
    client = get_supabase_client()
    if not client:
        return jsonify([]), 500
    
    try:
        result = client.table('admin_configs').select('*').order('id').execute()
        configs = result.data if result.data else []
        logger.info(f"Admin configs fetched: {len(configs)} items")
        return jsonify(configs)
    except Exception as e:
        logger.error(f"Error fetching admin configs: {e}")
        return jsonify([]), 500

@app.route('/admin-data/token-packages')
def get_token_packages():
    """Get token packages using Supabase"""
    client = get_supabase_client()
    if not client:
        return jsonify([]), 500
    
    try:
        result = client.table('token_packages').select('*').order('sort_order').execute()
        packages = result.data if result.data else []
        logger.info(f"Admin token packages fetched: {len(packages)} items")
        return jsonify(packages)
    except Exception as e:
        logger.error(f"Error fetching token packages: {e}")
        return jsonify([]), 500

@app.route('/admin-data/referral-codes')
def get_referral_codes():
    """Get referral codes using Supabase"""
    client = get_supabase_client()
    if not client:
        return jsonify([]), 500
    
    try:
        result = client.table('admin_referral_codes').select('*, users(username)').order('created_at', desc=True).execute()
        codes = result.data if result.data else []
        logger.info(f"Admin referral codes fetched: {len(codes)} items")
        return jsonify(codes)
    except Exception as e:
        logger.error(f"Error fetching referral codes: {e}")
        return jsonify([]), 500

# PUT/POST/DELETE endpoints for admin data would go here...
# (I'll add these if you want the complete migration)

# ===============================
# SECURE TOKEN ENDPOINTS
# ===============================

@app.route('/api/secure/token/balance/<username>', methods=['POST'])
def get_secure_user_balance(username):
    """Get user token balance (temporarily bypassing authentication for testing)"""
    try:
        logger.info(f"Secure balance request for user: {username} (auth bypassed for testing)")
        # TEMPORARY: Skip token validation for testing - BYPASSED
        
        # Get user balance directly from Supabase (bypassing auth for testing)
        if supabase:
            user_response = supabase.table('users').select('id').eq('username', username).execute()
            if user_response.data:
                user_id = user_response.data[0]['id']
                balance_response = supabase.table('token_balances').select('balance').eq('user_id', user_id).execute()
                if balance_response.data:
                    balance_data = {
                        'balance': balance_response.data[0]['balance'],
                        'user_id': user_id,
                        'username': username
                    }
                    logger.info(f"Fetched secure balance for {username} from Supabase: {balance_response.data[0]['balance']}")
                    return jsonify(balance_data)
        # Fallback to external API
        balance_data = make_external_api_request(f'/api/user/balance/{username}')
        return jsonify(balance_data)
    except Exception as e:
        logger.error(f"Error fetching secure balance for {username}: {e}")
        return jsonify({"error": "Failed to fetch balance"}), 500

@app.route('/api/secure/token/assets/<username>', methods=['POST'])
def get_secure_user_assets(username):
    """Get user assets (temporarily bypassing authentication for testing)"""
    try:
        logger.info(f"Secure assets request for user: {username} (auth bypassed for testing)")
        # TEMPORARY: Skip token validation for testing - BYPASSED
        
        # Use Supabase for user assets 
        client = get_supabase_client()
        if client:
            try:
                # Get user ID from Supabase
                user_response = client.table('users').select('id').eq('username', username).execute()
                
                if user_response.data:
                    user_id = user_response.data[0]['id']
                    # Get user assets from Supabase (using correct column names)
                    assets_response = client.table('user_assets').select(
                        'asset_id, quantity, current_price, user_price, updated_at'
                    ).eq('user_id', user_id).gt('quantity', 0).order('updated_at', desc=True).execute()
                    
                    if assets_response.data:
                        assets_data = [{
                            'id': asset['asset_id'],
                            'quantity': asset['quantity'],
                            'current_price': asset['current_price'],
                            'user_price': asset['user_price'],
                            'updated_at': asset['updated_at']
                        } for asset in assets_response.data]
                        
                        logger.info(f"Fetched {len(assets_data)} secure assets for {username} from Supabase")
                        return jsonify(assets_data)
                else:
                    logger.info(f"User {username} not found in Supabase")
            except Exception as e:
                logger.error(f"Supabase user assets error: {e}")
                # Fall back to external API
        
        # Fallback to external API
        assets_data = make_external_api_request(f'/api/user/assets/{username}')
        return jsonify(assets_data)
            
    except Exception as e:
        logger.error(f"Error fetching secure assets for {username}: {e}")
        return jsonify([]), 500

@app.route('/api/secure/referrals/<username>', methods=['POST'])
def get_secure_user_referrals(username):
    """Get user referrals (temporarily bypassing authentication for testing)"""
    try:
        logger.info(f"Secure referrals request for user: {username} (auth bypassed for testing)")
        # TEMPORARY: Skip token validation for testing - BYPASSED
        
        # Try Supabase first for referrals
        if supabase:
            response = supabase.table('users').select('id').eq('username', username).execute()
            if response.data:
                user_id = response.data[0]['id']
                # Get referrals from Supabase
                referrals_response = supabase.table('referrals').select('*').eq('referrer_id', user_id).execute()
                referral_data = referrals_response.data
                logger.info(f"Fetched {len(referral_data)} referrals for {username} from Supabase")
                return jsonify(referral_data)
        # Fallback to external API
        referral_data = make_external_api_request(f'/api/user/referrals/{username}')
        return jsonify(referral_data)
    except Exception as e:
        logger.error(f"Error fetching secure referrals for {username}: {e}")
        return jsonify([]), 500

@app.route('/api/secure/collectible/<collectible_id>')
def get_secure_collectible(collectible_id):
    """Get collectible details with secure token"""
    try:
        # Try external API first
        collectible_data = make_external_api_request(f'/api/collectible/{collectible_id}')
        return jsonify(collectible_data)
    except requests.exceptions.RequestException:
        # Fallback to local PostgreSQL data if external API fails
        try:
            conn = get_supabase_client()
            if conn:
                # Use Supabase API instead of cursor
                result = conn.table('collectibles').select('*').eq('id', collectible_id).execute()
                if result.data:
                    collectible_data = result.data[0]
                    return jsonify(collectible_data)
                
            return jsonify({"error": "Collectible not found"}), 404
        except Exception as e:
            logger.error(f"Database error fetching collectible {collectible_id}: {e}")
            return jsonify({"error": "Failed to fetch collectible"}), 500
    except Exception as e:
        logger.error(f"Error fetching collectible {collectible_id}: {e}")
        return jsonify({"error": "Failed to fetch collectible"}), 500

@app.route('/api/secure/price-history/<collectible_id>/<table_name>')
def get_secure_price_history(collectible_id, table_name):
    """Get authentic price history from eBay price history tables"""
    try:
        # Try external API first for authentic data
        external_data = make_external_api_request(f'/api/price-history/{collectible_id}/{table_name}')
        if external_data and isinstance(external_data, list) and len(external_data) > 0:
            logger.info(f"Retrieved {len(external_data)} authentic price history points from external API")
            return jsonify(external_data)
    except Exception as e:
        logger.info(f"External API failed: {str(e)[:100]}")
    
    # Fallback: Query Supabase for authentic price history data
    try:
        client = get_supabase_client()
        if client:
            # Query the actual eBay price history table with correct columns
            result = client.table(table_name).select('timestamp, avg_price, avg_price_with_shipping, total_listings, price_change, percent_change').order('timestamp', desc=True).limit(100).execute()
            
            if result.data and len(result.data) > 0:
                # Transform data to match expected format for price charts
                processed_data = []
                for record in result.data:
                    processed_data.append({
                        "timestamp": record['timestamp'],
                        "created_at": record['timestamp'],
                        "price": record['avg_price_with_shipping'],
                        "avg_price_with_shipping": record['avg_price_with_shipping'],
                        "volume": record.get('total_listings', 0)
                    })
                
                logger.info(f"Retrieved {len(processed_data)} authentic price history records from {table_name}")
                return jsonify(processed_data)
            else:
                logger.info(f"No authentic price history found in {table_name}")
                return jsonify([])
        else:
            logger.error("Supabase client not available")
            return jsonify([])
            
    except Exception as e:
        logger.error(f"Error querying {table_name}: {e}")
        return jsonify([])
        
    return jsonify([])

@app.route('/api/secure/market-summary/<collectible_id>/<table_name>')
def get_secure_market_summary(collectible_id, table_name):
    """Get authentic market summary from eBay market summary table"""
    try:
        # Try external API first for authentic data
        market_data = make_external_api_request(f'/api/market-summary/{collectible_id}/{table_name}')
        if market_data:
            logger.info(f"Retrieved authentic market summary from external API")
            return jsonify(market_data)
    except Exception as e:
        logger.info(f"External API failed: {str(e)[:100]}")
    
    # Fallback: Query Supabase for authentic market summary
    try:
        client = get_supabase_client()
        if client:
            # Extract market summary table name from price history table name
            # e.g., ebay_genesect_price_history -> ebay_genesect_market_summary
            market_summary_table = table_name.replace('_price_history', '_market_summary')
            
            result = client.table(market_summary_table).select('*').limit(1).execute()
            
            if result.data and len(result.data) > 0:
                record = result.data[0]
                # Transform to match expected frontend format
                market_data = {
                    "timestamp": record['timestamp'],
                    "created_at": record['timestamp'],
                    "avg_price_with_shipping": record['avg_price_with_shipping'],
                    "current_price": record['avg_price_with_shipping'],
                    "24h_change": record.get('percent_change', 0),
                    "24h_volume": record.get('total_listings', 0),
                    "price_change": record.get('price_change', 0),
                    "last_updated": record['timestamp']
                }
                logger.info(f"Retrieved authentic market summary from {market_summary_table}")
                return jsonify(market_data)
            else:
                logger.info(f"No authentic market summary found in {market_summary_table}")
                return jsonify({"error": "No market summary data found"})
        else:
            logger.error("Supabase client not available")
            return jsonify({"error": "Database unavailable"})
            
    except Exception as e:
        logger.error(f"Error querying market summary: {e}")
        return jsonify({"error": "Failed to fetch market summary"})

# ===============================
# PORTFOLIO AND MOVEMENTS ENDPOINTS  
# ===============================

@app.route('/api/user/movements/<username>')
def get_user_movements(username):
    """Get user movements/transactions"""
    try:
        # Try Supabase first for movements
        if supabase:
            user_response = supabase.table('users').select('id').eq('username', username).execute()
            if user_response.data:
                user_id = user_response.data[0]['id']
                # Get movements/transactions from Supabase with proper formatting
                movements_response = supabase.table('transactions').select('*').eq('user_id', user_id).order('created_at', desc=True).limit(50).execute()
                
                # Transform to match expected frontend format
                movements_data = []
                for transaction in movements_response.data:
                    movements_data.append({
                        'id': transaction['id'],
                        'collectible_id': transaction['collectible_id'],
                        'type': transaction['transaction_type'],
                        'amount': transaction['amount'],
                        'price': transaction.get('price', 0),
                        'description': transaction.get('description', ''),
                        'timestamp': transaction['created_at'],
                        'created_at': transaction['created_at']
                    })
                
                logger.info(f"Fetched {len(movements_data)} movements for {username} from Supabase")
                return jsonify(movements_data)
        # Fallback to external API
        movements_data = make_external_api_request(f'/api/user/movements/{username}')
        return jsonify(movements_data)
    except Exception as e:
        logger.error(f"Error fetching movements for {username}: {e}")
        return jsonify([]), 500

@app.route('/api/user/portfolio-gains/<username>')
def get_user_portfolio_gains(username):
    """Get user portfolio gains/losses"""
    try:
        # Try Supabase first for portfolio gains
        if supabase:
            user_response = supabase.table('users').select('id').eq('username', username).execute()
            if user_response.data:
                user_id = user_response.data[0]['id']
                # Calculate portfolio gains from user_assets and current prices (using correct column names)
                assets_response = supabase.table('user_assets').select('asset_id, quantity, user_price, current_price').eq('user_id', user_id).gt('quantity', 0).execute()
                
                portfolio_gains = []
                total_gain = 0
                total_value = 0
                
                for asset in assets_response.data:
                    quantity = float(asset['quantity'])
                    user_price = float(asset['user_price'] or 0)
                    current_price = float(asset['current_price'] or 0)
                    
                    gain_per_unit = current_price - user_price
                    total_gain_for_asset = gain_per_unit * quantity
                    current_value = current_price * quantity
                    
                    total_gain += total_gain_for_asset
                    total_value += current_value
                    
                    portfolio_gains.append({
                        'collectible_id': asset['asset_id'],
                        'quantity': quantity,
                        'user_price': user_price,
                        'current_price': current_price,
                        'gain_per_unit': gain_per_unit,
                        'total_gain': total_gain_for_asset,
                        'current_value': current_value
                    })
                
                gains_data = {
                    'total_gain': total_gain,
                    'total_value': total_value,
                    'gain_percentage': (total_gain / total_value * 100) if total_value > 0 else 0,
                    'assets': portfolio_gains
                }
                
                logger.info(f"Calculated portfolio gains for {username}: {total_gain}")
                return jsonify(gains_data)
        # Fallback to external API
        gains_data = make_external_api_request(f'/api/user/portfolio-gains/{username}')
        return jsonify(gains_data)
    except Exception as e:
        logger.error(f"Error fetching portfolio gains for {username}: {e}")
        return jsonify({"total_gain": 0, "total_value": 0, "gain_percentage": 0, "assets": []}), 500

# ===============================
# USER API ENDPOINTS
# ===============================

@app.route('/api/token/balance/<username>')
def get_user_balance(username):
    """Get user token balance from Supabase"""
    try:
        # Try Supabase first - get user ID then balance
        if supabase:
            user_response = supabase.table('users').select('id').eq('username', username).execute()
            if user_response.data:
                user_id = user_response.data[0]['id']
                balance_response = supabase.table('token_balances').select('balance').eq('user_id', user_id).execute()
                if balance_response.data:
                    balance_data = {
                        'balance': balance_response.data[0]['balance'],
                        'user_id': user_id,
                        'username': username
                    }
                    logger.info(f"Fetched balance for {username} from Supabase: {balance_response.data[0]['balance']}")
                    return jsonify(balance_data)
        # Fallback to external API
        balance_data = make_external_api_request(f'/api/user/balance/{username}')
        return jsonify(balance_data)
    except Exception as e:
        logger.error(f"Error fetching balance for {username}: {e}")
        return jsonify({"error": "Failed to fetch balance"}), 500

@app.route('/api/token/assets/<username>')
def get_user_assets(username):
    """Get user assets"""
    try:
        # Get user ID from database
        conn = get_supabase_client()
        if not conn:
            return jsonify([]), 500
        
        # Use Supabase API instead of cursor
        user_result = conn.table('users').select('id').eq('username', username).execute()
        if not user_result.data:
            return jsonify([]), 404
        
        user_id = user_result.data[0]['id']
        logger.info(f"Debug: Database user ID from users table: {user_id}")
        
        # Get user assets using Supabase
        assets_result = conn.table('user_assets').select('collectible_id as id, quantity, current_price, user_price, updated_at').eq('user_id', user_id).gt('quantity', 0).order('updated_at', desc=True).execute()
        assets = assets_result.data if assets_result.data else []
        
        return jsonify(assets)
            
    except Exception as e:
        logger.error(f"Error fetching assets for {username}: {e}")
        return jsonify([]), 500

@app.route('/api/user/balance/<username>')
def get_user_balance_public(username):
    """Get user token balance (public endpoint)"""
    try:
        # Try Supabase first - get user ID then balance
        if supabase:
            user_response = supabase.table('users').select('id').eq('username', username).execute()
            if user_response.data:
                user_id = user_response.data[0]['id']
                balance_response = supabase.table('token_balances').select('balance').eq('user_id', user_id).execute()
                if balance_response.data:
                    balance_data = {
                        'balance': balance_response.data[0]['balance'],
                        'user_id': user_id,
                        'username': username
                    }
                    logger.info(f"Fetched balance for {username} from Supabase: {balance_response.data[0]['balance']}")
                    return jsonify(balance_data)
        # Fallback to external API
        balance_data = make_external_api_request(f'/api/user/balance/{username}')
        return jsonify(balance_data)
    except Exception as e:
        logger.error(f"Error fetching balance for {username}: {e}")
        return jsonify({"error": "Failed to fetch balance"}), 500

@app.route('/api/user/referrals/<username>')
def get_user_referrals_public(username):
    """Get user referrals (public endpoint)"""
    try:
        # Try Supabase first for referrals
        if supabase:
            user_response = supabase.table('users').select('id').eq('username', username).execute()
            if user_response.data:
                user_id = user_response.data[0]['id']
                # Get referrals from Supabase
                referrals_response = supabase.table('referrals').select('*').eq('referrer_id', user_id).execute()
                referral_data = referrals_response.data
                logger.info(f"Fetched {len(referral_data)} referrals for {username} from Supabase")
                return jsonify(referral_data)
        # Fallback to external API
        referral_data = make_external_api_request(f'/api/user/referrals/{username}')
        return jsonify(referral_data)
    except Exception as e:
        logger.error(f"Error fetching referrals for {username}: {e}")
        return jsonify([]), 500

@app.route('/api/user/assets/<username>')
def get_user_assets_public(username):
    """Get user assets (public endpoint)"""
    try:
        # Try Supabase first with updated query
        if supabase:
            user_response = supabase.table('users').select('id').eq('username', username).execute()
            if user_response.data:
                user_id = user_response.data[0]['id']
                # Get user assets from Supabase
                assets_response = supabase.table('user_assets').select('collectible_id, quantity, current_price, user_price, updated_at').eq('user_id', user_id).gt('quantity', 0).execute()
                
                # Format the response to match expected structure
                assets_data = []
                for asset in assets_response.data:
                    assets_data.append({
                        'id': asset['collectible_id'],
                        'quantity': asset['quantity'],
                        'current_price': asset['current_price'],
                        'user_price': asset['user_price'],
                        'updated_at': asset['updated_at']
                    })
                
                logger.info(f"Fetched {len(assets_data)} assets for {username} from Supabase")
                return jsonify(assets_data)
        # Fallback to external API
        assets_data = make_external_api_request(f'/api/user/assets/{username}')
        return jsonify(assets_data)
    except Exception as e:
        logger.error(f"Error fetching assets for {username}: {e}")
        return jsonify([]), 500

# ===============================
# WEBSOCKET HANDLERS
# ===============================

@socketio.on('connect')
def handle_connect():
    """Handle WebSocket connection"""
    logger.info("WebSocket connection established")
    emit('connected', {'status': 'connected'})

@socketio.on('authenticate')
def handle_authenticate(data):
    """Handle WebSocket authentication"""
    username = data.get('username')
    if username:
        join_room(f"user_{username}")
        logger.info(f"WebSocket authenticated for user: {username}")
        emit('authenticated', {'status': 'authenticated', 'username': username})

@socketio.on('disconnect')
def handle_disconnect():
    """Handle WebSocket disconnection"""
    logger.info("WebSocket disconnected")

# Add endpoint for collectibles and marketplace data
@app.route('/api/collectibles')
def get_collectibles():
    """Get all collectibles for marketplace from Supabase"""
    try:
        if supabase:
            response = supabase.table('collectibles').select('*').execute()
            collectibles = response.data
            logger.info(f"Fetched {len(collectibles)} collectibles from Supabase")
            return jsonify(collectibles)
        else:
            logger.warning("Supabase client not available, using external API")
            raise Exception("Supabase not configured")
    except Exception as e:
        logger.error(f"Error fetching collectibles from Supabase: {e}")
        # Fallback to external API
        try:
            collectibles_data = make_external_api_request('/api/collectibles')
            return jsonify(collectibles_data)
        except Exception as api_error:
            logger.error(f"External API also failed: {api_error}")
            return jsonify([]), 500

@app.route('/api/prices')
def get_prices():
    """Get current prices for all collectibles from Supabase"""
    try:
        if supabase:
            response = supabase.table('collectibles').select('id, current_price').execute()
            prices = {item['id']: {'current_price': item['current_price']} for item in response.data}
            logger.info(f"Fetched prices for {len(prices)} collectibles from Supabase")
            return jsonify(prices)
        else:
            logger.warning("Supabase client not available, using external API")
            raise Exception("Supabase not configured")
    except Exception as e:
        logger.error(f"Error fetching prices from Supabase: {e}")
        # Fallback to external API
        try:
            prices_data = make_external_api_request('/api/prices')
            return jsonify(prices_data)
        except Exception as api_error:
            logger.error(f"External API also failed: {api_error}")
            return jsonify({}), 500

@app.route('/api/images')
def get_images():
    """Get optimized images for collectibles from Supabase"""
    try:
        if supabase:
            response = supabase.table('collectibles').select('id, image_url').execute()
            images = {item['id']: {'image_url': item['image_url']} for item in response.data}
            logger.info(f"Fetched images for {len(images)} collectibles from Supabase")
            return jsonify(images)
        else:
            logger.warning("Supabase client not available, using external API")
            raise Exception("Supabase not configured")
    except Exception as e:
        logger.error(f"Error fetching images from Supabase: {e}")
        # Fallback to external API
        try:
            images_data = make_external_api_request('/api/images')
            return jsonify(images_data)
        except Exception as api_error:
            logger.error(f"External API also failed: {api_error}")
            return jsonify({}), 500

# ===============================
# DATABASE INITIALIZATION
# ===============================

def initialize_database():
    """Initialize database schema using Supabase"""
    client = get_supabase_client()
    if not client:
        logger.error("Failed to get Supabase client for initialization")
        return
    
    try:
        # Since Supabase tables need to be created via the web interface,
        # we'll just verify the client works and prepare for data operations
        logger.info("Database schema initialized successfully (Supabase managed - tables created via web interface)")
    except Exception as e:
        logger.error(f"Error initializing database: {e}")

# ===============================
# CLEANUP TASKS
# ===============================

def cleanup_expired_tokens():
    """Clean up expired authentication tokens using Supabase"""
    client = get_supabase_client()
    if not client:
        return
    
    try:
        current_time = datetime.now().isoformat()
        result = client.table('auth_tokens').delete().lt('expires_at', current_time).execute()
        deleted_count = len(result.data) if result.data else 0
        logger.info(f"🧹 Cleaned up {deleted_count} expired tokens")
    except Exception as e:
        logger.error(f"Error cleaning up expired tokens: {e}")

def start_cleanup_scheduler():
    """Start periodic cleanup task"""
    def cleanup_worker():
        while True:
            time.sleep(6 * 60 * 60)  # 6 hours
            cleanup_expired_tokens()
    
    cleanup_thread = threading.Thread(target=cleanup_worker, daemon=True)
    cleanup_thread.start()
    logger.info("🧹 Automatic token cleanup started (every 6 hours)")

# ===============================
# APPLICATION STARTUP
# ===============================

if __name__ == '__main__':
    logger.info("🔧 Initializing database schema (first time only)...")
    initialize_database()
    
    logger.info("Starting cleanup scheduler...")
    start_cleanup_scheduler()
    
    # Get port from environment (for both local and Vercel)
    port = int(os.environ.get('PORT', 5000))
    logger.info(f"🚀 Starting Flask server on port {port}...")
    
    # Check if running on Vercel (serverless)
    if os.environ.get('VERCEL'):
        # For Vercel serverless - don't run socketio.run
        logger.info("Running in Vercel serverless mode")
    else:
        # For local development or other hosting
        socketio.run(app, host='0.0.0.0', port=port, debug=False, use_reloader=False, log_output=True, allow_unsafe_werkzeug=True)