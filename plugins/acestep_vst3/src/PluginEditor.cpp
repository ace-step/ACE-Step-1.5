#include "PluginEditor.h"

#include "PluginProcessor.h"
#include "V2Chrome.h"

namespace acestep::vst3
{
namespace
{
constexpr int kEditorWidth = 1080;
constexpr int kViewportHeight = 920;
constexpr int kContentHeight = 1280;
}  // namespace

void ACEStepVST3AudioProcessorEditor::ScrollContent::paint(juce::Graphics& g)
{
    v2::drawChassis(g, getLocalBounds());
}

ACEStepVST3AudioProcessorEditor::ACEStepVST3AudioProcessorEditor(
    ACEStepVST3AudioProcessor& processor)
    : juce::AudioProcessorEditor(&processor), processor_(processor)
{
    lookAndFeel_ = std::make_unique<V2LookAndFeel>();
    setLookAndFeel(lookAndFeel_.get());
    setSize(kEditorWidth, kViewportHeight);
    viewport_.setScrollBarsShown(true, false, true, false);
    viewport_.setViewedComponent(&scrollContent_, false);
    addAndMakeVisible(viewport_);

    for (auto* component : {static_cast<juce::Component*>(&statusStrip_),
                            static_cast<juce::Component*>(&synthPanel_),
                            static_cast<juce::Component*>(&transport_),
                            static_cast<juce::Component*>(&compositionLane_),
                            static_cast<juce::Component*>(&resultDeck_),
                            static_cast<juce::Component*>(&previewDeck_)})
    {
        scrollContent_.addAndMakeVisible(*component);
    }

    configureLabels();
    configureEditors();
    configureSelectors();
    syncFromProcessor();
    refreshResultSelector();
    refreshStatusViews();
    startTimerHz(4);
}

ACEStepVST3AudioProcessorEditor::~ACEStepVST3AudioProcessorEditor()
{
    setLookAndFeel(nullptr);
}

void ACEStepVST3AudioProcessorEditor::paint(juce::Graphics& g)
{
    g.fillAll(v2::kChassisOuter);
}

void ACEStepVST3AudioProcessorEditor::resized()
{
    viewport_.setBounds(getLocalBounds());
    scrollContent_.setSize(juce::jmax(kEditorWidth, viewport_.getWidth() - 12), kContentHeight);

    auto bounds = scrollContent_.getLocalBounds().reduced(26);
    statusStrip_.setBounds(bounds.removeFromTop(96));
    bounds.removeFromTop(14);

    auto upper = bounds.removeFromTop(492);
    bounds.removeFromTop(14);
    auto compositionBounds = bounds.removeFromTop(286);
    bounds.removeFromTop(14);
    auto lower = bounds;

    auto synthBounds = upper.removeFromLeft((upper.getWidth() * 11) / 20);
    synthPanel_.setBounds(synthBounds.reduced(0, 2));
    upper.removeFromLeft(14);
    transport_.setBounds(upper.reduced(0, 2));

    compositionLane_.setBounds(compositionBounds);

    auto resultBounds = lower.removeFromTop(196);
    resultDeck_.setBounds(resultBounds);
    lower.removeFromTop(14);
    previewDeck_.setBounds(lower);
}

void ACEStepVST3AudioProcessorEditor::timerCallback()
{
    processor_.pumpBackendWorkflow();
    refreshResultSelector();
    refreshStatusViews();
}
}  // namespace acestep::vst3
