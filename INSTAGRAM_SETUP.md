# Instagram auto-posting setup (Our Scene NYC)

How to get `INSTAGRAM_ACCESS_TOKEN` and `INSTAGRAM_ACCOUNT_ID` so the weekly
carousel posts to **@ourscenenyc** automatically.

We use the **Instagram API with Instagram Login** (host `graph.instagram.com`).
This is the right path because **@ourscenenyc is a standalone account with no
Facebook Page** — and this API explicitly *"does not require a Facebook Page to
be linked to the Instagram professional account."*
([docs](https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/))

> **Skip the tester-invite flow.** The tester invite that wasn't showing up is a
> leftover from the old Basic Display API. With Instagram Login you generate a
> token directly in the App Dashboard by logging into Instagram in a popup — no
> invite to accept, and **no need to link a personal Facebook account** (that
> workaround leads to the Facebook-*Page* path, which is more friction, not less).

---

## Prerequisite: @ourscenenyc must be a Professional account

Content publishing only works for **Business** or **Creator** accounts (not
personal). In the Instagram app on your phone, logged in as @ourscenenyc:

- **Settings and privacy → Account type and tools → Switch to professional
  account** → choose **Business** (or Creator).

If it's already professional, skip this.

---

## Step 1 — Add the Instagram product to your Meta app

You already have a Business-type app. In the [Meta App Dashboard](https://developers.facebook.com/apps/):

1. Open your app.
2. Left sidebar → **+ Add product** → find **Instagram** → **Set up**.
3. In the Instagram section, click **API setup with Instagram business login**.

You'll see three numbered sub-sections. The ones that matter:

- **1. Generate access tokens** — where we'll create the token (Step 3).
- **2. Configure webhooks** — *ignore.*
- **3. Set up Instagram business login** — *Business login settings.*

---

## Step 2 — Make sure the publish permission is enabled

Under **Set up Instagram business login → Business login settings → Permissions**
(or the Permissions list for the Instagram use case), confirm these scopes are
present:

- `instagram_business_basic`  *(added by default)*
- **`instagram_business_content_publish`**  ← **you must add this one** — it's
  required to publish, and is *not* on by default.

> The old names (`instagram_basic`, `instagram_content_publish`) were turned off
> on **Jan 27, 2025** — make sure you're using the `instagram_business_*` names.

Because the app only ever posts to **your own** account, you do **not** need App
Review or Advanced Access — **Standard Access (development mode) is enough.**
*"If your app only serves your Instagram professional account or an account you
manage, Standard Access is all your app needs."*
([docs](https://developers.facebook.com/docs/instagram-platform/overview/))

---

## Step 3 — Generate the access token (the part that was blocking you)

In **1. Generate access tokens**:

1. Click **Add account**.
2. Click **Continue** and **log in to @ourscenenyc** in the popup window.
3. Approve the permissions → **Save** → **Got it**.
4. Back in the dashboard, click **Generate token** next to @ourscenenyc.
5. **Copy the token.**

This token is **short-lived (1 hour)** — fine for the next step, but **not** what
goes in the GitHub secret. Convert it to a long-lived one first ⤵.

---

## Step 4 — Exchange for a long-lived (60-day) token

You need your **Instagram App Secret**: dashboard → **App settings → Basic →
Instagram App Secret** (or shown in the API-setup section). Then run, replacing
the two placeholders:

```bash
curl -s -G "https://graph.instagram.com/access_token" \
  --data-urlencode "grant_type=ig_exchange_token" \
  --data-urlencode "client_secret=YOUR_INSTAGRAM_APP_SECRET" \
  --data-urlencode "access_token=SHORT_LIVED_TOKEN_FROM_STEP_3"
```

The response looks like:

```json
{ "access_token": "IGAAR...long...", "token_type": "bearer", "expires_in": 5183944 }
```

That `access_token` is your **long-lived, 60-day** token → this is
`INSTAGRAM_ACCESS_TOKEN`.

---

## Step 5 — Get the account id

```bash
curl -s -G "https://graph.instagram.com/v25.0/me" \
  --data-urlencode "fields=user_id,username" \
  --data-urlencode "access_token=LONG_LIVED_TOKEN"
```

```json
{ "user_id": "178414xxxxxxxxxxx", "username": "ourscenenyc" }
```

That `user_id` is your `INSTAGRAM_ACCOUNT_ID`. (Confirm `username` is `ourscenenyc`.)

---

## Step 6 — Add both as GitHub repo secrets

GitHub → repo → **Settings → Secrets and variables → Actions → New repository
secret**, or via CLI:

```bash
gh secret set INSTAGRAM_ACCESS_TOKEN --body "LONG_LIVED_TOKEN"
gh secret set INSTAGRAM_ACCOUNT_ID  --body "178414xxxxxxxxxxx"
```

(`GEMINI_API_KEY` and `BUTTONDOWN_API_KEY` should already be set.)

---

## Step 7 — Dry-run test (no public post)

Instagram has no private/sandbox post, so the safe test creates the carousel
container — exercising the token, the publish permission, the account id, and
the public image fetch — but **stops before publishing**.

GitHub → repo → **Actions → Weekly Newsletter → Run workflow → mode: `test`**.

That run will: scrape → curate → build the carousel images → push them to `main`
→ then **dry-run** the post. A green run means everything is wired correctly and
the next scheduled Sunday send will post for real. Watch the
**"Instagram carousel DRY-RUN"** step logs for `🧪 DRY RUN — container … ready`.

---

## Token expiry — important for automation

The long-lived token lasts **60 days**. The job runs weekly, so it's always used
in time, **but the token itself still expires 60 days after you generate it** and
the workflow will start failing.

Options:
- **Now:** set a calendar reminder ~55 days out to regenerate (Steps 3–4 + 6).
- **Better (ask me to build it):** a small scheduled job that calls
  `GET https://graph.instagram.com/refresh_access_token?grant_type=ig_refresh_token&access_token=…`
  every ~50 days and updates the secret so it never expires.

---

## If the Instagram-Login path won't work — fallback

If Step 3 refuses to attach @ourscenenyc (rare), the alternative is the
**Facebook-Login path**, which needs a **Facebook *Page*** (not a personal
account):

1. Create a Facebook Page (free).
2. On the Page → **Settings → Linked accounts → Instagram** → connect @ourscenenyc.
3. Add the **Facebook Login for Business** product; generate a **Page** access
   token with `instagram_basic`, `instagram_content_publish`, `pages_show_list`.
4. Get the IG id: `GET /<page-id>?fields=instagram_business_account`.
5. Switch the code base URL back to `graph.facebook.com` (set
   `INSTAGRAM_API_VERSION` and edit `_base_url()` in `src/instagram/poster.py`).

This is heavier (extra Page + linking), so only use it if the primary path fails.
