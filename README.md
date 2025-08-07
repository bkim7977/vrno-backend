# VRNO Backend

Flask backend API for the VRNO Token Market application with Supabase integration.

## Features

- 🔥 **Flask 3.0 Backend**: Complete API server with WebSocket support
- 🗄️ **Supabase Integration**: PostgreSQL database with real-time capabilities
- 🔐 **Secure Authentication**: One-time tokens and API key validation
- 💰 **Token Management**: User balances, transactions, and asset tracking
- 📊 **Market Data**: Real-time collectible prices and market analytics
- 🎯 **Admin Panel**: Complete administrative interface
- 🚀 **Vercel Ready**: Optimized for serverless deployment

## Quick Start

### Environment Variables

**IMPORTANT**: Copy `.env.example` to `.env` and fill in your actual values:

```bash
cp .env.example .env
# Edit .env with your actual API keys
```

Required environment variables:
- `VRNO_API_KEY` - Your VRNO API key
- `SUPABASE_URL` - Your Supabase project URL  
- `SUPABASE_SERVICE_ROLE_KEY` - Your Supabase service role key
- Other optional variables for email, SMS, PayPal integration

See `.env.example` for the complete list.

### Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export SUPABASE_URL="https://your-project.supabase.co"
export SUPABASE_SERVICE_ROLE_KEY="your_service_key"
export VRNO_API_KEY="your_api_key"

# Run the server
python api/app.py
```

The server will start on http://localhost:5000

## Deployment

### Deploy to Vercel

1. **Deploy Backend First**:
   ```bash
   # Make sure you're in the vrno-backend directory
   vercel --prod
   ```

2. **Set Environment Variables** in Vercel dashboard:
   - `SUPABASE_URL`
   - `SUPABASE_SERVICE_ROLE_KEY`
   - `VRNO_API_KEY`
   - Other API keys as needed

3. **Get Backend URL**: After deployment, note the backend URL (e.g., `https://vrno-backend.vercel.app`)

## License

This project is proprietary software for VRNO Token Market.
