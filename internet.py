#!/usr/bin/env python3
import requests
from bs4 import BeautifulSoup
import urllib3

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def check_backup_internet():
    home_url = "https://datapass.de/home"
    try:
        # Step 1: Access the home page with SSL verification disabled
        response = requests.get(home_url, verify=False)
        response.raise_for_status()
        #print("Successfully accessed:", home_url)
        #print("Status Code:", response.status_code)
        #print("\nHome page content snippet:")
        #print(response.text[:500])
        
        # Step 2: Parse the HTML and locate the product container with class "pass-offer-card"
        soup = BeautifulSoup(response.text, "html.parser")
        product_container = None

        for container in soup.find_all("p"):
            if "das Mobilfunknetz notwendig" in container.get_text():
                return "PRIMARY"

        for container in soup.find_all("section", class_="data-pass-instance"):
            if  "Unlimited Daypass" in container.get_text():
                return "BACKUP_PASS_ACTIVE"
    
        return "BACKUP_PASS_INACTIVE"

    except requests.RequestException as e:
        print("An error occurred while accessing the page:")
        print(e)
        return "ERROR"


def book_internet_pass():
    home_url = "https://datapass.de/home"
    try:
        # Step 1: Access the home page with SSL verification disabled
        response = requests.get(home_url, verify=False)
        response.raise_for_status()
        print("Successfully accessed:", home_url)
        print("Status Code:", response.status_code)
        print("\nHome page content snippet:")
        print(response.text[:500])
        
        # Step 2: Parse the HTML and locate the product container with class "pass-offer-card"
        soup = BeautifulSoup(response.text, "html.parser")
        product_container = None

        for container in soup.find_all("section", class_="data-pass-instance"):
            if  "Unlimited Daypass" in container.get_text():
                return "ALREADY_BOOKED"
        
        for container in soup.find_all("div", class_="pass-offer-card"):
            if "Unlimited Daypass" in container.get_text():
                product_container = container
                break
        
        if not product_container:
            print("Could not find the product box containing 'Unlimited Daypass'.")
            return "ERROR"
        
        # Step 3: Within that container, find the "Auswählen" button
        ausw_btn = None
        for btn in product_container.find_all(["a", "button"]):
            if "Auswählen" in btn.get_text():
                ausw_btn = btn
                break
        
        if not ausw_btn:
            print("Could not find the 'Auswählen' button in the 'Unlimited Daypass' box.")
            return "ERROR"
        
        print("\nFound the 'Auswählen' button.")
        
        # Step 4: Determine the URL to navigate to from the button (if it's an anchor)
        if ausw_btn.name == "a":
            target_url = ausw_btn.get("href")
            if target_url.startswith("/"):
                target_url = "https://datapass.de" + target_url
        else:
            print("The 'Auswählen' button is not an anchor tag. Additional handling is required.")
            return "ERROR"
        
        print("Navigating to the 'Auswählen' page at:", target_url)
        
        # Step 5: Access the "Auswählen" page with SSL verification disabled
        target_response = requests.get(target_url, verify=False)
        target_response.raise_for_status()
        print("Successfully accessed the 'Auswählen' page.")
        print("Status Code:", target_response.status_code)
        print("\n'Auswählen' page content snippet:")
        print(target_response.text[:500])
        
        # Step 6: In the returned HTML, locate the form with the submit input "Zahlungspflichtig bestellen"
        soup_target = BeautifulSoup(target_response.text, "html.parser")
        submit_button = soup_target.find("input", {"type": "submit", "value": "Zahlungspflichtig bestellen"})
        if not submit_button:
            print("Could not find the 'Zahlungspflichtig bestellen' submit button.")
            return "ERROR"
        
        form = submit_button.find_parent("form")
        if not form:
            print("Could not find the parent form for the submit button.")
            return "ERROR"
        
        # Collect form data from all input elements within the form
        form_data = {}
        for input_tag in form.find_all("input"):
            name = input_tag.get("name")
            if not name:
                continue
            value = input_tag.get("value", "")
            form_data[name] = value
        
        # Determine the form's action URL
        form_action = form.get("action")
        if not form_action.startswith("http"):
            form_action = "https://datapass.de" + form_action
        
        print("\nSubmitting form to:", form_action)
        print("Form data:", form_data)
        
        # Step 7: Submit the form using a POST request with the form data
        form_response = requests.post(form_action, data=form_data, verify=False)
        form_response.raise_for_status()
        print("Successfully submitted the form with 'Zahlungspflichtig bestellen'")
        print("Status Code:", form_response.status_code)
        print("\nResponse content snippet:")
        print(form_response.text[:500])

        return "SUCCESS"
        
    except requests.RequestException as e:
        print("An error occurred while accessing the page:")
        print(e)
        return "ERROR"
