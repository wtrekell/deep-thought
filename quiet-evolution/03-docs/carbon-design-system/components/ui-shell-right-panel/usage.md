---
tool: web
url: "https://carbondesignsystem.com/components/UI-shell-right-panel/usage/"
mode: documentation
title: "UI shell right panel – Carbon Design SystemOpen menuOpen menu"
word_count: 756
processed_date: 2026-04-14T05:07:21.499936+00:00
---

# UI shell right panel

  * [Usage](https://carbondesignsystem.com/components/UI-shell-right-panel/usage/)
  * [Style](https://carbondesignsystem.com/components/UI-shell-right-panel/style/)
  * [Code](https://carbondesignsystem.com/components/UI-shell-right-panel/code/)
  * [Accessibility](https://carbondesignsystem.com/components/UI-shell-right-panel/accessibility/)

The right panel is part of the Carbon UI shell. A shell is a collection of components shared by all products within a platform. It provides a common set of interaction patterns that persist between and across products.

  * Live demo
  * General guidance
  * Anatomy
  * Behavior

## Live demo

Theme selector

White

Open menu

* * *

Variant selector

Header w/ sideNav

Open menu

* * *

This live demo contains only a preview of functionality and styles available for this component. View the [full demo](https://react.carbondesignsystem.com/?path=/story/components-ui-shell-header--header-w-side-nav&globals=theme:white) on Storybook for additional information such as its version, controls, and API documentation.

### Accessibility testing status

For every latest release, Carbon runs tests on all components to meet the [accessibility requirements](https://www.ibm.com/able/requirements/requirements/). These different statuses report the work that Carbon has done in the back end. These tests appear only when the components are stable.

##### [Default stateTested](https://carbondesignsystem.com/components/UI-shell-right-panel/accessibility/#accessibility-testing-status)

##### [Advanced statesTested](https://carbondesignsystem.com/components/UI-shell-right-panel/accessibility/#accessibility-testing-status)

##### [Screen readerManually tested](https://carbondesignsystem.com/components/UI-shell-right-panel/accessibility/#accessibility-testing-status)

##### [Keyboard navigationTested](https://carbondesignsystem.com/components/UI-shell-right-panel/accessibility/#accessibility-testing-status)

## Resources

##### [UI Shell template](https://sketch.cloud/s/6a8e1d7b-f00a-4d8d-9d83-79ecf4dc12a0)

## General guidance

The UI shell is made up of three components: The [header](https://carbondesignsystem.com/components/UI-shell-header/usage), the [left panel](https://carbondesignsystem.com/components/UI-shell-right-panel/usage), and the right panel. All three can be used independently, but the components were designed to work together.

Shell UI component|   
---|---  
Header| The highest level of navigation. The header can be used on its own for simple products or be used to trigger the left and right panels.  
Left panel| An optional panel that is used for a product’s navigation.  
Right panel| An optional panel that shows additional system level actions or content associated with a system icon in the header.  
  
UI shell components

## Anatomy

The right panel is invoked by icons on the right side of the header, and remains anchored to that icon. Right panels have a consistent width, span the full height of the viewport, and are flush to the right edge of the viewport.

Note that the switcher also lives in a right panel.

The right panel configured as an empty header panel (left) and a switcher (right).

#### Switcher item

A switcher item is anything that changes what product, offering, or property occupies the UI shell. Consider moments in a product when you switch from a calendar to a mailbox, from Kubernetes to Catalog. These items belong in the switcher.

#### Switcher divider

A switcher divider groups similar switcher items. You can use a divider to set apart a parent domain, group child domains similar in hierarchy to the parent, and set apart additional resources. The divider should not be used to separate every switcher item.

### Switcher

The far right header icon is reserved for the switcher icon. The switcher icon and the switcher panel should only be used together.

Positioned the switcher to the far right.

Do not position other icons to the right of the switcher.

Do not use another icon for the switcher.

## Behavior

#### Expansion

Right panels always float over page content, and always remain anchored to their associated icon. You can have multiple right panels, but only one can be expanded at any time.

#### Dismissal

Once expanded, the panel’s associated icon is outlined, with its bottom border flowing into the panel. To dismiss the panel, a user must select an item, or click or tap the header icon.

#### Selected state

There is no selected state for right panel items. Even if a user is currently within one of the panel items, the item remains unselected.

[Edit this page on GitHub](https://github.com/carbon-design-system/carbon-website/edit/main/src/pages/components/UI-shell-right-panel/usage.mdx)

  * [Contact us](https://www.carbondesignsystem.com/help/contact-us)
  * [Privacy](https://www.ibm.com/privacy)
  * [Terms of use](https://www.ibm.com/legal)
  * [Accessibility](https://www.ibm.com/able)
  * [IBM.com](https://www.ibm.com/)

  * [Medium](https://medium.com/carbondesign)
  * [𝕏](https://x.com/_carbondesign)

Have questions? Email us   
at [carbon@us.ibm.com](mailto:carbon@us.ibm.com)   
or open an issue on [GitHub.](https://github.com/carbon-design-system/carbon-website/issues/new)

React Components version ^1.105.0  
Last updated 09 April 2026  
Copyright © 2026 IBM

IBM web domains

ibm.com, ibm.org, ibm-zcouncil.com, insights-on-business.com, jazz.net, mobilebusinessinsights.com, promontory.com, proveit.com, ptech.org, s81c.com, securityintelligence.com, skillsbuild.org, softlayer.com, storagecommunity.org, think-exchange.com, thoughtsoncloud.com, alphaevents.webcasts.com, ibm-cloud.github.io, ibmbigdatahub.com, bluemix.net, mybluemix.net, ibm.net, ibmcloud.com, galasa.dev, blueworkslive.com, swiss-quantum.ch, blueworkslive.com, cloudant.com, ibm.ie, ibm.fr, ibm.com.br, ibm.co, ibm.ca, community.watsonanalytics.com, datapower.com, skills.yourlearning.ibm.com, bluewolf.com, carbondesignsystem.com, openliberty.io 

About cookies on this site Our websites require some cookies to function properly (required). In addition, other cookies may be used with your consent to analyze site usage, improve the user experience and for advertising. For more information, please review your cookie preferences options. By visiting our website, you agree to our processing of information as described in IBM’s[privacy statement](https://www.ibm.com/privacy).  To provide a smooth navigation, your cookie preferences will be shared across the IBM web domains listed here.

Accept all More options

Cookie Preferences