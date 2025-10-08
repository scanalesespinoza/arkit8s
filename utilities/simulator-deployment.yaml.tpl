apiVersion: apps/v1
kind: Deployment
metadata:
  name: {name}
  namespace: {namespace}
  labels:
    app: {name}
    arkit8s.simulator: "true"
  annotations:
    architecture.domain: business
    architecture.function: {function_annotation}
    architecture.simulates: {simulated_component}
    architecture.part_of: arkit8s
spec:
  replicas: 1
  selector:
    matchLabels:
      app: {name}
  template:
    metadata:
      labels:
        app: {name}
        arkit8s.simulator: "true"
        arkit8s.simulates: {simulated_component}
    spec:
      containers:
        - name: availability-simulator
          image: registry.access.redhat.com/ubi10/ubi-minimal
          env:
            - name: BEHAVIOR
              value: "{behavior}"
          command:
            - sh
            - -c
            - |
              echo "[$(date -u)] starting with BEHAVIOR=$BEHAVIOR"
              if [ "$BEHAVIOR" = "restart" ]; then
                sleep 60
                echo "[$(date -u)] simulating crash to trigger restart"
                exit 1
              elif [ "$BEHAVIOR" = "notready" ]; then
                while true; do
                  sleep 30
                done
              else
                while true; do
                  echo "[$(date -u)] running normally (BEHAVIOR=$BEHAVIOR)"
                  sleep 30
                done
              fi
          livenessProbe:
            exec:
              command:
                - sh
                - -c
                - exit 0
            initialDelaySeconds: 15
            periodSeconds: 20
          readinessProbe:
            exec:
              command:
                - sh
                - -c
                - |
                  if [ "$BEHAVIOR" = "notready" ]; then
                    exit 1
                  else
                    exit 0
                  fi
            initialDelaySeconds: 5
            periodSeconds: 10
