####
#
# fiction-dl
# Copyright (C) (2020 - 2021) Benedykt Synakiewicz <dreamcobbler@outlook.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
####

"""
FlareSolverr integration for bypassing Cloudflare protection.

FlareSolverr is required for Cloudflare-protected sites like fanfiction.net.
To set up FlareSolverr, run it via Docker:

    docker run -d --name flaresolverr -p 8191:8191 ghcr.io/flaresolverr/flaresolverr:latest

For more info: https://github.com/FlareSolverr/FlareSolverr
"""

#
#
#
# Imports.
#
#
#

# Application.

import fiction_dl.Configuration as Configuration

# Standard packages.

import logging
import requests
import time
from typing import Optional

#
#
#
# Globals.
#
#
#

# Session ID for reusing browser instance (much faster for multiple requests)
_flaresolverr_session: Optional[str] = None

#
#
#
# Functions.
#
#
#

def IsFlareSolverrRunning(port: int = 8191) -> bool:
    
    ##
    #
    # Checks if FlareSolverr is running and responding.
    #
    # @param port The port to check.
    #
    # @return True if running and responding, False otherwise.
    #
    ##
    
    try:
        response = requests.get(f"http://localhost:{port}/", timeout=5)
        return response.status_code == 200
    except:
        return False


def GetFlareSolverrURL(port: int = 8191) -> str:
    
    ##
    #
    # Returns the FlareSolverr API URL.
    #
    # @param port The port FlareSolverr is running on.
    #
    # @return The API URL string.
    #
    ##
    
    return f"http://localhost:{port}/v1"


def CreateSession(port: int = 8191) -> Optional[str]:
    
    ##
    #
    # Creates a FlareSolverr session (reuses browser instance for speed).
    #
    # @param port The FlareSolverr port.
    #
    # @return Session ID string, or None on failure.
    #
    ##
    
    global _flaresolverr_session
    
    if _flaresolverr_session:
        return _flaresolverr_session
    
    apiURL = GetFlareSolverrURL(port)
    
    try:
        response = requests.post(
            apiURL,
            json={"cmd": "sessions.create"},
            timeout=30
        )
        response.raise_for_status()
        
        data = response.json()
        
        if data.get("status") == "ok":
            _flaresolverr_session = data.get("session")
            logging.info(f"FlareSolverr session created: {_flaresolverr_session}")
            return _flaresolverr_session
        else:
            logging.warning(f"Failed to create FlareSolverr session: {data.get('message')}")
            return None
            
    except Exception as e:
        logging.warning(f"Failed to create FlareSolverr session: {e}")
        return None


def DestroySession(port: int = 8191):
    
    ##
    #
    # Destroys the current FlareSolverr session.
    #
    # @param port The FlareSolverr port.
    #
    ##
    
    global _flaresolverr_session
    
    if not _flaresolverr_session:
        return
    
    apiURL = GetFlareSolverrURL(port)
    
    try:
        requests.post(
            apiURL,
            json={
                "cmd": "sessions.destroy",
                "session": _flaresolverr_session
            },
            timeout=10
        )
        logging.info(f"FlareSolverr session destroyed: {_flaresolverr_session}")
    except:
        pass
    
    _flaresolverr_session = None


def SolveChallenge(url: str, port: int = 8191, maxTimeout: int = 60000, maxRetries: int = 3) -> Optional[str]:
    
    ##
    #
    # Uses FlareSolverr to solve Cloudflare challenge and get page content.
    # Uses sessions for faster subsequent requests.
    #
    # @param url        The URL to fetch.
    # @param port       The FlareSolverr port.
    # @param maxTimeout Maximum timeout in milliseconds.
    # @param maxRetries Maximum number of retry attempts.
    #
    # @return The page HTML content, or None on failure.
    #
    ##
    
    global _flaresolverr_session
    
    apiURL = GetFlareSolverrURL(port)
    
    # Try to create/use a session for faster requests
    session = CreateSession(port)
    
    for attempt in range(maxRetries):
        try:
            requestData = {
                "cmd": "request.get",
                "url": url,
                "maxTimeout": maxTimeout
            }
            
            # Use session if available (much faster after first request)
            if session:
                requestData["session"] = session
            
            response = requests.post(
                apiURL,
                json=requestData,
                timeout=maxTimeout // 1000 + 30
            )
            response.raise_for_status()
            
            data = response.json()
            
            if data.get("status") == "ok":
                return data.get("solution", {}).get("response")
            else:
                errorMsg = data.get('message', 'Unknown error')
                logging.warning(f"FlareSolverr error (attempt {attempt + 1}/{maxRetries}): {errorMsg}")
                
                # If session error, try to recreate it
                if "session" in errorMsg.lower():
                    _flaresolverr_session = None
                    session = CreateSession(port)
                
        except requests.exceptions.Timeout:
            logging.warning(f"FlareSolverr timeout (attempt {attempt + 1}/{maxRetries}) for {url}")
            if attempt < maxRetries - 1:
                time.sleep(2)
                
        except Exception as e:
            logging.warning(f"FlareSolverr request failed (attempt {attempt + 1}/{maxRetries}): {e}")
            if attempt < maxRetries - 1:
                time.sleep(2)
    
    logging.error(f"FlareSolverr failed after {maxRetries} attempts for {url}")
    return None
