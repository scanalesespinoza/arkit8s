NAMESPACE=rhbk
HOST=http://rhbk.apps-crc.testing/

.PHONY: crc-dev wait admin open destroy

crc-dev:
        oc kustomize bootstrap/operators/rhbk --load-restrictor=LoadRestrictionsNone | oc apply -f -
        @echo "Waiting for RHBK operator to be ready..."
        @oc wait --for=condition=Succeeded -n $(NAMESPACE) csv -l operators.coreos.com/rhbk-operator.$(NAMESPACE) --timeout=300s
        oc apply -k support-domain/identity

wait:
	@echo "Waiting for Keycloak to be ready..."
	@oc -n $(NAMESPACE) wait --for=condition=Ready statefulset/rhbk --timeout=300s

admin:
	@echo "Username: $$(oc -n $(NAMESPACE) get secret rhbk-initial-admin -o jsonpath='{.data.username}' | base64 -d)"
	@echo "Password: $$(oc -n $(NAMESPACE) get secret rhbk-initial-admin -o jsonpath='{.data.password}' | base64 -d)"

open:
	@echo $(HOST)

destroy:
        -oc delete -k support-domain/identity
        -oc kustomize bootstrap/operators/rhbk --load-restrictor=LoadRestrictionsNone | oc delete -f -
