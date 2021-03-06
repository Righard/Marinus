#!/usr/bin/python3

# Copyright 2018 Adobe. All rights reserved.
# This file is licensed to you under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License. You may obtain a copy
# of the License at http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software distributed under
# the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR REPRESENTATIONS
# OF ANY KIND, either express or implied. See the License for the specific language
# governing permissions and limitations under the License.

"""
This module manages interactions with the Rapid7 OpenData service.
Access to the service requires a complicated handshake with their Okta plugin.
"""

import configparser
import json
import subprocess
import time

import requests
from html.parser import HTMLParser
from requests.auth import HTTPBasicAuth


class MyHTMLParser(HTMLParser):
    """
    Create a subclass to find the files within the authenticated HTML page.
    """
    any_url = ""
    a_url = ""
    aaaa_url = ""
    rdns_url = ""
    base_url = ""

    def set_base_location(self, base_location):
        self.base_url = base_location

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            for attr in attrs:
                if self.any_url == "" and attr[0] == "href" and attr[1].endswith("fdns_any.json.gz"):
                    print(attr[1])
                    self.any_url =  self.base_url + attr[1]
                elif self.a_url == "" and attr[0] == "href" and attr[1].endswith("fdns_a.json.gz"):
                    print(attr[1])
                    self.a_url = self.base_url + attr[1]
                elif self.aaaa_url == "" and attr[0] == "href" and attr[1].endswith("fdns_aaaa.json.gz"):
                    print(attr[1])
                    self.aaaa_url = self.base_url + attr[1]
                elif self.rdns_url == "" and attr[0] == "href" and attr[1].endswith("rdns.json.gz"):
                    print(attr[1])
                    self.rdns_url = self.base_url + attr[1]


class MySAMLParser(HTMLParser):
    """
    This sub-class searches an HTML response for the SAML data
    """
    saml_response = ""
    relay_state = ""

    def handle_starttag(self, tag, attrs):
        if tag == "input":
            found_saml = False
            found_relay = False
            for attr in attrs:
                if self.saml_response == "" and attr[0] == "name" and attr[1] == "SAMLResponse" :
                    found_saml = True
                elif self.relay_state == "" and attr[0] == "name" and attr[1] == "RelayState":
                    found_relay = True
                elif found_saml and attr[0] == "value":
                    self.saml_response = attr[1]
                elif found_relay and attr[0] == "value":
                    self.relay_state = attr[1]


class Rapid7(object):
    """
    This class is designed for interacting with Rapid7
    """

    rapid7_config_file = 'connector.config'
    USERNAME = None
    PASSWORD = None
    AUTH_URL = None
    BASE_URL = "https://opendata.rapid7.com"
    FDNS_PATH = "/sonar.fdns_v2/"
    RDNS_PATH = "/sonar.rdns_v2/"
    debug = False
    PID_FILE = None


    @staticmethod
    def _get_config_setting(config, section, key, type='str'):
        """
        Retrieves the key value from inside the section the connector.config file.

        This function is in multiple modules because it was originally designed
        that each module could be standalone.

        :param config: A Python ConfigParser object
        :param section: The section where the key exists
        :param key: The name of the key to retrieve
        :param type: (Optional) Specify 'boolean' to convert True/False strings to booleans.
        :return: A string or boolean from the config file.
        """
        try:
            if type == 'boolean':
                result = config.getboolean(section, key)
            else:
                result = config.get(section, key)
        except configparser.NoSectionError:
            print('Warning: ' + section + ' does not exist in config file')
            if type == 'boolean':
                return 0
            else:
                return ""
        except configparser.NoOptionError:
            print('Warning: ' + key + ' does not exist in the config file')
            if type == 'boolean':
                return 0
            else:
                return ""
        except configparser.Error as err:
            print('Warning: Unexpected error with config file')
            print(str(err))
            if type == 'boolean':
                return 0
            else:
                return ""

        return result


    def _init_Rapid7(self, config):
        self.AUTH_URL = self._get_config_setting(config, "Rapid7", "rapid7.auth_url")
        self.USERNAME = self._get_config_setting(config, "Rapid7", "rapid7.username")
        self.PASSWORD = self._get_config_setting(config, "Rapid7", "rapid7.password")


    def __init__(self, config_file="", debug=False):
        if config_file != "":
            self.rapid7_config_file = config_file
        self.debug = debug

        config = configparser.ConfigParser()
        list = config.read(self.rapid7_config_file)
        if len(list) == 0:
            print('Error: Could not find the config file')
            exit(0)

        self._init_Rapid7(config)


    def find_file_locations(self, s, list_type, job_name, jobs_collection):
        """
        In order to login, it is necessary go through several Okta steps since Rapid 7 doesn't have an API key.
        """
        if list_type == "rdns":
            list_location = self.BASE_URL + self.RDNS_PATH
        else:
            list_location = self.BASE_URL + self.FDNS_PATH


        # Assembled as a string because their site is extremely picky on the format.
        auth_payload = '{"username":"' + self.USERNAME + '","password":"' + self.PASSWORD.replace('"','\\"') + '",'
        auth_payload = auth_payload + '"options":{"warnBeforePasswordExpired":true,"multiOptionalFactorEnroll":true}}'

        res = requests.post(self.AUTH_URL, data=auth_payload, headers={"Accept": "application/json",
                                                                    "Content-Type": "application/json",
                                                                    "X-Okta-User-Agent-Extended": "okta-signin-widget-2.6.0",
                                                                    "Host": "rapid7ipimseu.okta-emea.com",
                                                                    "Origin": "https://insight.rapid7.com"})

        if res.status_code != 200:
            print("Failed login")
            print(res.text)
            exit(0)

        data = json.loads(res.text)


        # This URL is embedded in the JS from the login page. Should try to dynamically extract it in the next revision
        # view-source:https://insight.rapid7.com/login
        res = s.get("https://rapid7ipimseu.okta-emea.com/login/sessionCookieRedirect?checkAccountSetupComplete=true&token=" + data['sessionToken'] + "&redirectUrl=https://rapid7ipimseu.okta-emea.com/home/template_saml_2_0/0oatgdg8ruitg9ZTr0i6/3079")

        if res.status_code != 200:
            print("Unable to do cookie redirect")
            print(res.text)
            exit(0)


        # Fetch the SAML Tokens for the Rapid7 site
        saml_parser = MySAMLParser()
        saml_parser.feed(res.text)
        saml_data = {"RelayState": saml_parser.relay_state, "SAMLResponse": saml_parser.saml_response}

        res = s.post("https://insight.rapid7.com/saml/SSO", data=saml_data)

        if res.status_code != 200:
            print("SSO Failure!")
            print(res.text)
            exit(0)


        # A final redirect step for the Open Data site
        res = s.get("https://insight.rapid7.com/redirect/doRedirect")


        # Finally download the list of files available to authenticated users.
        req = s.get(list_location)

        if req.status_code != 200:
            print("Bad Request")
            jobs_collection.update_one({'job_name': job_name},
                                    {'$currentDate': {"updated" :True},
                                        "$set": {'status': 'ERROR'}})
            exit(0)

        parser = MyHTMLParser()
        parser.set_base_location(self.BASE_URL)
        parser.feed(req.text)
        return parser
