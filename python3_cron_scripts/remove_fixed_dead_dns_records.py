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
This script will try to remove fixed dead DNS records from Marinus.
A dead DNS Record is one where an existing DNS record points at a non-existant resource.
For instance, let's say that foo.example.org points to foo.s3.amazonaws.com.
However, if foo.s3.amazonaws.com doesn't exist, then you have a dead DNS record.
Periodically, DNS records are cleaned up and the record for foo.example.org is deleted.
Once foo.example.org is deleted, we can remove it from the Dead DNS tracking list.
"""

import json
import time
from datetime import datetime

import requests
from bson.objectid import ObjectId

from libs3 import DNSManager, MongoConnector, GoogleDNS


def main():
    """
    Begin Main...
    """

    now = datetime.now()
    print ("Starting: " + str(now))

    mongo_connector = MongoConnector.MongoConnector()
    jobs_collection = mongo_connector.get_jobs_connection()
    dead_dns_collection = mongo_connector.get_dead_dns_connection()

    google_dns = GoogleDNS.GoogleDNS()

    results = dead_dns_collection.find({})

    for result in results:
        time.sleep(1)
        lookup_result = google_dns.fetch_DNS_records(result['fqdn'])
        if lookup_result == []:
            print ("Removing " + result['fqdn'])
            dead_dns_collection.remove({"_id":ObjectId(result['_id'])})

    # Record status
    jobs_collection.update_one({'job_name': 'dead_dns_cleanup'},
                               {'$currentDate': {"updated": True},
                                "$set": {'status': 'COMPLETE'}})

    now = datetime.now()
    print ("Ending: " + str(now))

if __name__ == "__main__":
    main()
