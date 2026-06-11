# Secrets Management, Email Alerts, & WebRTC TURN Setup

To make the email alert system and WebRTC webcam stream function correctly on your Hugging Face Space deployment, you must configure **Repository Secrets** in your Space Settings. The `.env` configuration file is gitignored and is not pushed to the cloud.

---

## 1. Required Repository Secrets

Navigate to your Hugging Face Space page, go to **Settings** > **Variables and Secrets** > **New Secret**, and add the following keys:

### SMTP Email Secrets
| Secret Key | Description | Example Value |
| :--- | :--- | :--- |
| `SMTP_USERNAME` | The sender email address from which alert reports are dispatched. | `workzflow32@gmail.com` |
| `SMTP_PASSWORD` | The email account's password (or 16-character Google App Password). | `akxlivvuwcdoqiza` |
| `EMERGENCY_RECEIVER_EMAIL` | The destination emergency contact email address. | `ashiksjc2025@gmail.com` |
| `SMTP_SERVER` | SMTP host server address (defaults to `smtp.gmail.com` if omitted). | `smtp.gmail.com` |
| `SMTP_PORT` | SMTP port (defaults to `587` if omitted). | `587` |

### WebRTC STUN/TURN Secrets (Required for Hugging Face Camera stream)
Hugging Face containers run behind strict firewalls and reverse proxies that block standard STUN over UDP. Relayed TURN over TCP (usually port 443 turns/turn) is required.
| Secret Key | Description | Example Value |
| :--- | :--- | :--- |
| `TURN_URL` | The TURN server hostname (optional; if left blank, defaults to `global.metered.ca`). | `global.metered.ca:443` |
| `TURN_USERNAME` | Your TURN server credential username (obtained from Metered.ca). | `your_metered_username` |
| `TURN_PASSWORD` | Your TURN server credential password (obtained from Metered.ca). | `your_metered_password` |

---

## 2. Generating a Google App Password (For Gmail sender)

If your sender email (`SMTP_USERNAME`) is a Gmail account, standard passwords will be blocked by Google's security policies. You must generate an App Password:
1. Log into your Google Account dashboard.
2. Go to **Security** and enable **2-Step Verification** if not already enabled.
3. Under 2-Step Verification, scroll to the bottom and select **App passwords**.
4. Create an app password named `Driver Safety System` and copy the 16-character passcode generated (e.g. `akxlivvuwcdoqiza`).
5. Save this passcode as `SMTP_PASSWORD` in your Hugging Face Space Secrets.

---

## 3. Obtaining Free TURN Credentials (For WebRTC Camera Stream)

1. Go to [Metered.ca](https://www.metered.ca/) and register for a free account (no credit card required).
2. Go to the dashboard and navigate to **TURN Server** details.
3. Copy the **Username** and **Password** credentials.
4. Save them as `TURN_USERNAME` and `TURN_PASSWORD` in your Hugging Face Space Secrets.
5. Once added, the dashboard will automatically pick them up and route the WebRTC camera stream over secure TCP, which bypasses Hugging Face's sandboxed network blockages.
