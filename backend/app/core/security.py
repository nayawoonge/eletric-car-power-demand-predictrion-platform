"""
Security utilities and authentication middleware
"""
import hashlib
import secrets
import re
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from pathlib import Path

from fastapi import HTTPException, Depends, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import logging

logger = logging.getLogger(__name__)

# Simple API key store - In production, use proper secrets management
API_KEYS = {
    "admin": "pdp_admin_" + hashlib.sha256(b"power_demand_predictor_admin").hexdigest()[:32],
    "read": "pdp_read_" + hashlib.sha256(b"power_demand_predictor_read").hexdigest()[:32],
}

class SecurityValidator:
    """Security validation utilities"""
    
    @staticmethod
    def validate_station_id(station_id: str) -> str:
        """
        Validate and sanitize station ID
        
        Args:
            station_id: Station identifier
            
        Returns:
            Sanitized station ID
            
        Raises:
            HTTPException: If station_id is invalid
        """
        if not station_id:
            raise HTTPException(status_code=400, detail="Station ID is required")
        
        # Allow alphanumeric, hyphens, and underscores only
        if not re.match(r'^[a-zA-Z0-9_-]+$', station_id):
            raise HTTPException(
                status_code=400, 
                detail="Invalid station ID format. Only alphanumeric characters, hyphens, and underscores allowed."
            )
        
        # Length limit
        if len(station_id) > 50:
            raise HTTPException(status_code=400, detail="Station ID too long (max 50 characters)")
            
        return station_id.strip()
    
    @staticmethod
    def validate_filename(filename: str) -> str:
        """
        Validate and sanitize filename
        
        Args:
            filename: Original filename
            
        Returns:
            Sanitized filename
            
        Raises:
            HTTPException: If filename is invalid
        """
        if not filename:
            raise HTTPException(status_code=400, detail="Filename is required")
        
        # Extract just the filename without path
        safe_name = Path(filename).name
        
        # Additional security checks
        if '..' in safe_name or '/' in safe_name or '\\' in safe_name:
            raise HTTPException(status_code=400, detail="Invalid filename")
        
        # Check for hidden files
        if safe_name.startswith('.'):
            raise HTTPException(status_code=400, detail="Hidden files not allowed")
        
        # Length limit
        if len(safe_name) > 255:
            raise HTTPException(status_code=400, detail="Filename too long")
        
        return safe_name
    
    @staticmethod
    def validate_file_content(content: bytes, filename: str) -> bool:
        """
        Validate file content for security threats
        
        Args:
            content: File content bytes
            filename: Filename
            
        Returns:
            True if content is safe
            
        Raises:
            HTTPException: If content is unsafe
        """
        # Check file size (additional check)
        max_size = 100 * 1024 * 1024  # 100MB
        if len(content) > max_size:
            raise HTTPException(status_code=400, detail="File too large")
        
        # Check for CSV file signature (basic MIME type validation)
        if not filename.lower().endswith('.csv'):
            raise HTTPException(status_code=400, detail="Only CSV files are allowed")
        
        # Check for malicious patterns in first few bytes
        content_start = content[:1024].decode('utf-8', errors='ignore').lower()
        
        # Look for suspicious patterns
        dangerous_patterns = [
            '<script', '<?php', '#!/bin/', 'exec(', 'eval(', 
            'system(', '__import__', 'subprocess'
        ]
        
        for pattern in dangerous_patterns:
            if pattern in content_start:
                raise HTTPException(
                    status_code=400, 
                    detail="File contains potentially malicious content"
                )
        
        return True


class APIKeyAuth:
    """API Key based authentication"""
    
    def __init__(self):
        self.security = HTTPBearer(auto_error=False)
    
    async def get_current_user(
        self, 
        credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False)),
        x_api_key: Optional[str] = Header(None)
    ) -> Dict[str, Any]:
        """
        Extract user information from API key
        
        Args:
            credentials: Bearer token from Authorization header
            x_api_key: API key from X-API-Key header
            
        Returns:
            User information dictionary
            
        Raises:
            HTTPException: If authentication fails
        """
        # Try to get API key from either header
        api_key = None
        
        if credentials:
            api_key = credentials.credentials
        elif x_api_key:
            api_key = x_api_key
        
        if not api_key:
            raise HTTPException(
                status_code=401, 
                detail="API key required",
                headers={"WWW-Authenticate": "Bearer"}
            )
        
        # Validate API key
        user_role = None
        for role, valid_key in API_KEYS.items():
            if api_key == valid_key:
                user_role = role
                break
        
        if not user_role:
            logger.warning(f"Invalid API key attempt: {api_key[:10]}...")
            raise HTTPException(
                status_code=401,
                detail="Invalid API key"
            )
        
        logger.info(f"Authenticated user with role: {user_role}")
        
        return {
            "role": user_role,
            "api_key": api_key,
            "authenticated_at": datetime.now().isoformat()
        }
    
    async def require_admin(
        self, 
        current_user: Dict[str, Any] = Depends(lambda self=None: self.get_current_user() if self else APIKeyAuth().get_current_user())
    ) -> Dict[str, Any]:
        """
        Require admin role for access
        
        Args:
            current_user: Current authenticated user
            
        Returns:
            User information if admin
            
        Raises:
            HTTPException: If user is not admin
        """
        if current_user.get("role") != "admin":
            raise HTTPException(
                status_code=403,
                detail="Admin access required"
            )
        
        return current_user


# Global instances
security_validator = SecurityValidator()
api_key_auth = APIKeyAuth()

# Dependency functions
async def get_current_user() -> Dict[str, Any]:
    """Dependency to get current authenticated user"""
    return await api_key_auth.get_current_user()

async def require_admin() -> Dict[str, Any]:
    """Dependency to require admin access"""
    return await api_key_auth.require_admin()

def validate_station_id(station_id: str) -> str:
    """Dependency to validate station ID"""
    return security_validator.validate_station_id(station_id)


class RateLimiter:
    """Simple in-memory rate limiter"""
    
    def __init__(self):
        self.requests: Dict[str, list] = {}
        self.window_seconds = 60
        self.max_requests = 100  # per minute
    
    def is_allowed(self, client_ip: str) -> bool:
        """
        Check if request is allowed based on rate limit
        
        Args:
            client_ip: Client IP address
            
        Returns:
            True if request is allowed
        """
        now = datetime.now()
        
        # Clean old requests
        if client_ip in self.requests:
            self.requests[client_ip] = [
                req_time for req_time in self.requests[client_ip]
                if (now - req_time).seconds < self.window_seconds
            ]
        else:
            self.requests[client_ip] = []
        
        # Check rate limit
        if len(self.requests[client_ip]) >= self.max_requests:
            return False
        
        # Add current request
        self.requests[client_ip].append(now)
        return True


# Global rate limiter instance
rate_limiter = RateLimiter()