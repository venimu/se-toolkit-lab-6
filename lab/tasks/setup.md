# Lab setup

- [1. Required steps](#1-required-steps)
  - [1.1. Clean up the previous lab (on your VM)](#11-clean-up-the-previous-lab-on-your-vm)
  - [1.2. Set up your fork](#12-set-up-your-fork)
    - [1.2.1. Fork the course instructors' repo](#121-fork-the-course-instructors-repo)
    - [1.2.2. Go to your fork](#122-go-to-your-fork)
    - [1.2.3. Enable issues](#123-enable-issues)
    - [1.2.4. Add a classmate as a collaborator](#124-add-a-classmate-as-a-collaborator)
    - [1.2.5. Protect your `main` branch](#125-protect-your-main-branch)
  - [1.3. Clone your fork and set up the environment (on your laptop)](#13-clone-your-fork-and-set-up-the-environment-on-your-laptop)
  - [1.4. Deploy to your VM](#14-deploy-to-your-vm)
    - [1.4.1. Connect to your VM and clone the repo](#141-connect-to-your-vm-and-clone-the-repo)
    - [1.4.2. Prepare the environment (on the VM)](#142-prepare-the-environment-on-the-vm)
    - [1.4.3. Start the services (on the VM)](#143-start-the-services-on-the-vm)
  - [1.5. Populate the database](#15-populate-the-database)
  - [1.6. Verify the deployment](#16-verify-the-deployment)
  - [1.7. Set up a coding agent](#17-set-up-a-coding-agent)
  - [1.8. Set up the autochecker](#18-set-up-the-autochecker)

## 1. Required steps

> [!NOTE]
> This lab builds on the same tools and setup from previous labs.
> If you completed Labs 4–5, most tools are already installed.
> The main changes are: a new repo, populating data, and setting up LLM access.

> [!NOTE]
> This lab needs your university email, GitHub alias, and VM IP in the Autochecker bot <https://t.me/auchebot>. If you haven't registered, do so now. If you want to change something, contact your TA.

### 1.1. Clean up the previous lab (on your VM)

> [!IMPORTANT]
> Remove previous lab containers and volumes to free up ports and disk space on your VM.

1. [Connect to your VM](../../wiki/vm.md#connect-to-the-vm).
2. Navigate to the previous lab's project directory:

   ```terminal
   cd ~/se-toolkit-lab-5
   ```

3. Stop and remove all containers and volumes:

   ```terminal
   docker compose --env-file .env.docker.secret down -v
   ```

4. Go back to the home directory:

   ```terminal
   cd ~
   ```

> [!NOTE]
> If you didn't do Lab 5, try `cd ~/se-toolkit-lab-4` instead.
> If neither directory exists, skip this step.

### 1.2. Set up your fork

#### 1.2.1. Fork the course instructors' repo

1. Fork the [lab's repo](https://github.com/inno-se-toolkit/se-toolkit-lab-6).

We refer to your fork as `fork` and to the original repo as `upstream`.

#### 1.2.2. Go to your fork

1. Go to your fork, it should look like `https://github.com/<your-github-username>/se-toolkit-lab-6`.

#### 1.2.3. Enable issues

1. [Enable issues](../../wiki/github.md#enable-issues).

#### 1.2.4. Add a classmate as a collaborator

1. [Add a collaborator](../../wiki/github.md#add-a-collaborator) — your partner.
2. Your partner should add you as a collaborator in their repo.

#### 1.2.5. Protect your `main` branch

1. [Protect a branch](../../wiki/github.md#protect-a-branch).

### 1.3. Clone your fork and set up the environment (on your laptop)

1. Clone your fork to your local machine:

   ```terminal
   git clone https://github.com/<your-github-username>/se-toolkit-lab-6
   ```

2. Open the forked repo in `VS Code`.

3. Go to `VS Code Terminal`, [check that the current directory is `se-toolkit-lab-6`](../../wiki/shell.md#check-the-current-directory-is-directory-name), and install `Python` dependencies:

   ```terminal
   uv sync --dev
   ```

4. Create the environment file:

   ```terminal
   cp .env.docker.example .env.docker.secret
   ```

5. Configure the autochecker API credentials.

   The ETL pipeline fetches data from the autochecker dashboard API.
   Open `.env.docker.secret` and set:

   ```text
   AUTOCHECKER_EMAIL=<your-email>@innopolis.university
   AUTOCHECKER_PASSWORD=<your-github-username><your-telegram-alias>
   ```

   Example: if your GitHub username is `johndoe` and your Telegram alias is `jdoe`, the password is `johndoejdoe`.

   > [!IMPORTANT]
   > The credentials must match your autochecker bot registration.

### 1.4. Deploy to your VM

#### 1.4.1. Connect to your VM and clone the repo

1. Connect to your VM:

   ```terminal
   ssh <vm-user>@<vm-ip>
   ```

   If unable, see [how to connect to your VM](../../wiki/vm.md#connect-to-the-vm).

2. Clone your fork on the VM:

   ```terminal
   cd ~
   git clone https://github.com/<your-github-username>/se-toolkit-lab-6.git
   cd se-toolkit-lab-6
   ```

#### 1.4.2. Prepare the environment (on the VM)

1. Create the `Docker` environment file:

   ```terminal
   cp .env.docker.example .env.docker.secret
   ```

2. Edit `.env.docker.secret`:

   ```terminal
   nano .env.docker.secret
   ```

   Set your autochecker API credentials:

   ```text
   AUTOCHECKER_EMAIL=<your-email>@innopolis.university
   AUTOCHECKER_PASSWORD=<your-github-username><your-telegram-alias>
   ```

   Set your API key (remember it — you'll need it for the agent):

   ```text
   API_KEY=set-it-to-something-and-remember-it
   ```

   Save and exit: `Ctrl+X`, then `y`, then `Enter`.

#### 1.4.3. Start the services (on the VM)

1. Start the services in the background:

   ```terminal
   docker compose --env-file .env.docker.secret up --build -d
   ```

2. Check that the containers are running:

   ```terminal
   docker compose --env-file .env.docker.secret ps --format "table {{.Service}}\t{{.Status}}"
   ```

   You should see all four services running:

   ```terminal
   SERVICE    STATUS
   app        Up 50 seconds
   caddy      Up 49 seconds
   pgadmin    Up 50 seconds
   postgres   Up 55 seconds (healthy)
   ```

   <details><summary><b>Troubleshooting (click to open)</b></summary>

   <h4>Port conflict (<code>port is already allocated</code>)</h4>

   [Clean up `Docker`](../../wiki/docker.md#clean-up-docker), then run the `docker compose up` command again.

   <h4>Containers exit immediately</h4>

   Rebuild all containers from scratch:

   ```terminal
   docker compose --env-file .env.docker.secret down -v
   docker compose --env-file .env.docker.secret up --build -d
   ```

   </details>

### 1.5. Populate the database

The database starts empty. You need to run the ETL pipeline to populate it with data from the autochecker API.

1. Open in a browser: `http://<your-vm-ip>:42002/docs`

   You should see the Swagger UI page.

2. [Authorize in Swagger](../../wiki/swagger.md#authorize-in-swagger-ui) with the `API_KEY` you set in `.env.docker.secret`.

3. Run the ETL sync by calling `POST /pipeline/sync` in Swagger UI.

   You should get a response showing the number of items and logs loaded:

   ```json
   {
     "items_loaded": 120,
     "logs_loaded": 5000
   }
   ```

   > [!NOTE]
   > The exact numbers depend on how much data the autochecker API has.
   > As long as both numbers are greater than 0, the sync worked.

4. Verify data by calling `GET /items/`.

   You should get a non-empty array of items.

### 1.6. Verify the deployment

1. Open `http://<your-vm-ip>:42002/docs` in a browser.

   You should see the Swagger UI with all endpoints.

2. Open `http://<your-vm-ip>:42002/` in a browser.

   You should see the frontend. Enter your API key to connect.

3. Switch to the **Dashboard** tab.

   You should see charts with analytics data (score distribution, submissions timeline, group performance, task pass rates).

> [!IMPORTANT]
> If the dashboard shows no data or errors, make sure:
> - The ETL sync completed successfully (step 1.5)
> - You entered the correct API key in the frontend
> - Try selecting a different lab in the dropdown (e.g., `lab-04`)

### 1.7. Set up a coding agent

A coding agent can help you write code, explain concepts, and debug issues.

- Method 1: [Set up a `Qwen Code`-based agent](../../wiki/qwen.md#set-up-qwen-code).
- Method 2: [Choose another coding agent](../../wiki/coding-agents.md#choose-and-use-a-coding-agent).

### 1.8. Set up the autochecker

[Set up the autochecker](../../wiki/autochecker.md#set-up-the-autochecker).

[Check the task using the autochecker `Telegram` bot](../../wiki/autochecker.md#check-the-task-using-the-autochecker-bot).

---

Congrats! Your system is deployed with data. Now go to the [tasks](../../README.md#tasks).
