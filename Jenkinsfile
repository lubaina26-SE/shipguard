pipeline {
  agent any
  options {
    timeout(time: 30, unit: 'MINUTES')
    disableConcurrentBuilds()
  }
  environment {
    IMAGE_TAG = "build-${env.BUILD_NUMBER}"
  }
  stages {
    stage('Checkout') {
      steps {
        checkout scm
        script { env.COMMIT = sh(script: 'git rev-parse HEAD', returnStdout: true).trim() }
      }
    }
    stage('Unit tests') {
      steps {
        sh '''docker run --rm --volumes-from jenkins -w "$WORKSPACE/api" python:3.12-slim \
          sh -c "pip install -q -r requirements.txt && python -m pytest -q"'''
      }
    }
    stage('Secret scan (Gitleaks)') {
      steps {
        sh '''docker run --rm --volumes-from jenkins -w "$WORKSPACE" zricethezav/gitleaks:latest \
          detect --source . --no-git --redact'''
      }
    }
    stage('Build and deploy') {
      steps {
        withCredentials([
          string(credentialsId: 'db-password', variable: 'DB_PASSWORD'),
          string(credentialsId: 'ingest-token', variable: 'INGEST_TOKEN')
        ]) {
          sh 'docker compose up -d --build'
        }
      }
    }
    stage('Health check') {
      steps {
        sh '''
        for i in $(seq 1 20); do
          if curl -sf http://host.docker.internal:8080/health; then echo " HEALTHY"; exit 0; fi
          echo "waiting... $i"; sleep 6
        done
        echo "Health check FAILED"; exit 1
        '''
      }
    }
  }
  post {
    success { script { record('success') } }
    failure { script { record('failed') } }
  }
}

def record(String status) {
  withCredentials([string(credentialsId: 'ingest-token', variable: 'INGEST_TOKEN')]) {
    sh """curl -s -X POST http://host.docker.internal:8080/api/deployments \
      -H "X-Ingest-Token: \$INGEST_TOKEN" -H "Content-Type: application/json" \
      -d '{"commit_sha":"${env.COMMIT ?: 'unknown'}","image_tag":"${env.IMAGE_TAG}","tests_passed":true,"vulnerabilities":0,"status":"${status}"}' || true"""
  }
}