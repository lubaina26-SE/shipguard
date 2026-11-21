pipeline {
  agent any
  options {
    timeout(time: 40, unit: 'MINUTES')
    disableConcurrentBuilds()
  }
  environment {
    IMAGE_TAG = "build-${env.BUILD_NUMBER}"
  }
  stages {
    stage('Checkout') {
      steps {
        checkout scm
        script {
          env.COMMIT = sh(script: 'git rev-parse HEAD', returnStdout: true).trim()
          env.TESTS_OK = 'false'
          env.VULNS = '0'
          env.DEPLOY_STARTED = 'false'
        }
      }
    }
    stage('Unit tests') {
      steps {
        sh '''docker run --rm --volumes-from jenkins -w "$WORKSPACE/api" python:3.12-slim \
          sh -c "pip install -q -r requirements.txt && python -m pytest -q"'''
        script { env.TESTS_OK = 'true' }
      }
    }
    stage('Code security (Bandit)') {
      steps {
        sh '''docker run --rm --volumes-from jenkins -w "$WORKSPACE/api" python:3.12-slim \
          sh -c "pip install -q bandit && bandit -r app -ll"'''
      }
    }
    stage('Secret scan (Gitleaks)') {
      steps {
        sh '''docker run --rm --volumes-from jenkins -w "$WORKSPACE" zricethezav/gitleaks:latest \
          detect --source . --no-git --redact'''
      }
    }
    stage('Dependency scan (Trivy)') {
      steps {
        sh '''docker run --rm --volumes-from jenkins -v trivy-cache:/root/.cache -w "$WORKSPACE" \
          aquasec/trivy:latest fs --scanners vuln --severity CRITICAL --ignore-unfixed --exit-code 1 api'''
      }
    }
    stage('Build images') {
      steps {
        withCredentials([
          string(credentialsId: 'db-password', variable: 'DB_PASSWORD'),
          string(credentialsId: 'ingest-token', variable: 'INGEST_TOKEN')
        ]) {
          sh 'docker compose build'
        }
        sh '''docker tag shipguard-api:latest shipguard-api:$IMAGE_TAG
              docker tag shipguard-web:latest shipguard-web:$IMAGE_TAG'''
      }
    }
    stage('Image scan (Trivy)') {
      steps {
        script {
          def total = 0
          for (img in ['shipguard-api:latest', 'shipguard-web:latest']) {
            def n = sh(script: """docker run --rm -v /var/run/docker.sock:/var/run/docker.sock -v trivy-cache:/root/.cache aquasec/trivy:latest image --quiet --severity HIGH,CRITICAL --ignore-unfixed --format json ${img} | grep -c VulnerabilityID || true""", returnStdout: true).trim()
            total += (n ? n.toInteger() : 0)
          }
          env.VULNS = total.toString()
        }
        sh '''for i in shipguard-api:latest shipguard-web:latest; do
          docker run --rm -v /var/run/docker.sock:/var/run/docker.sock -v trivy-cache:/root/.cache \
            aquasec/trivy:latest image --severity HIGH,CRITICAL --ignore-unfixed --exit-code 0 $i
        done'''
        sh '''for i in shipguard-api:latest shipguard-web:latest; do
          docker run --rm -v /var/run/docker.sock:/var/run/docker.sock -v trivy-cache:/root/.cache \
            aquasec/trivy:latest image --quiet --severity CRITICAL --ignore-unfixed --exit-code 1 $i || exit 1
        done'''
      }
    }
    stage('Deploy') {
      steps {
        script {
          env.PREV_API = sh(script: "docker inspect -f '{{.Image}}' shipguard-api-1 2>/dev/null || true", returnStdout: true).trim()
          env.PREV_WEB = sh(script: "docker inspect -f '{{.Image}}' shipguard-web-1 2>/dev/null || true", returnStdout: true).trim()
          env.DEPLOY_STARTED = 'true'
        }
        withCredentials([
          string(credentialsId: 'db-password', variable: 'DB_PASSWORD'),
          string(credentialsId: 'ingest-token', variable: 'INGEST_TOKEN')
        ]) {
          sh 'docker compose up -d --no-build'
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
    failure {
      script {
        if (env.DEPLOY_STARTED == 'true') { rollback(); record('rolled_back') }
        else { record('failed') }
      }
    }
  }
}

def rollback() {
  withCredentials([
    string(credentialsId: 'db-password', variable: 'DB_PASSWORD'),
    string(credentialsId: 'ingest-token', variable: 'INGEST_TOKEN')
  ]) {
    sh '''
    if [ -n "$PREV_API" ] && [ -n "$PREV_WEB" ]; then
      docker tag "$PREV_API" shipguard-api:latest
      docker tag "$PREV_WEB" shipguard-web:latest
      docker compose up -d --no-build
      echo "ROLLED BACK to previous version"
    else
      echo "No previous version to roll back to"
    fi
    '''
  }
}

def record(String status) {
  withCredentials([string(credentialsId: 'ingest-token', variable: 'INGEST_TOKEN')]) {
    sh """sleep 10; curl -s -X POST http://host.docker.internal:8080/api/deployments \
      -H "X-Ingest-Token: \$INGEST_TOKEN" -H "Content-Type: application/json" \
      -d '{"commit_sha":"${env.COMMIT ?: 'unknown'}","image_tag":"${env.IMAGE_TAG}","tests_passed":${env.TESTS_OK ?: 'false'},"vulnerabilities":${env.VULNS ?: '0'},"status":"${status}"}' || true"""
  }
}